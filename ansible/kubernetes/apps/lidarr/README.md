# Lidarr on the Talos cluster (Argo CD)

Lidarr runs from the bjw-s **app-template** chart (5.3.0) as an Argo CD
Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/lidarr.yaml`. Syncs are manual,
pruning is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/lidarr/docker-compose.yml`
(app `docker.io/linuxserver/lidarr:3.1.0`, port 8686). All state is
the `/config` directory (SQLite database, config.xml, logs); there
is no separate database to dump — the cutover is a verified file
copy, and Lidarr's own startup migrations handle the rest.

Exposure is **tailnet-only**: the pod mirrors the RomM shape —
userspace Tailscale sidecar → in-pod Caddy (8443, Cloudflare DNS-01)
→ Lidarr on 127.0.0.1:8686, at `lidarr.tail.davegallant.ca`,
replacing the LXC's host-level `tailnet_caddy` role.

**qBittorrent does not move.** It keeps its LXC, its static LAN IP,
and its OPNsense → Mullvad policy route (Batch D design, Dave,
2026-10-23). This pod reaches the qBittorrent API over the LAN
exactly as the LXC does today; the CiliumNetworkPolicy carries the
single new rule that split requires. The shared media tree is a
static NFS PV (`storage.yaml`) mounted at `/mnt` — the identical
path the LXC uses — so every path in Lidarr's database stays true
and hardlink imports keep working: NFS link/rename are server-side
operations within the export, unaffected by which client asks. The
tree never moves and is never Velero-backed-up (TrueNAS snapshots +
Drive sync).

Secrets stay in Vault and outside Argo's ownership:
`lidarr-caddy-external` from `playbooks/talos-cluster/gitops-secrets.yml`,
and the bootstrap-only one-use `lidarr-tailscale-auth`. There is
deliberately no app Secret: Lidarr's API key and its qBittorrent
credentials live in `config.xml`, which arrives with the copied
`/config`.

Backups: Velero Schedule `lidarr-daily` (in the values) with pod
annotation `backup.velero.io/backup-volumes: config`. The network
policy is the house default-deny CiliumNetworkPolicy, in the values
as `rawResources.defaultDenyNetworkPolicy`, plus the qBittorrent
exception described there.

## Step 0 — verify before staging (do not skip)

1. **Media export.** On the lidarr LXC, record what backs `/mnt`:
   `findmnt -no SOURCE,FSTYPE /mnt`. Correct the share in
   `storage.yaml` if it is not the `/mnt/tank/media` export
   (if `/mnt` spans several exports, follow the multi-PV note in
   `storage.yaml` instead). The in-pod `/mnt` tree must be
   identical to the LXC's. Do the same for `/music`
   (`findmnt -no SOURCE,FSTYPE /music`): `storage.yaml` assumes
   the TrueNAS `/mnt/tank/media/Music` export — if `/music` is
   instead a symlink or bind into the `/mnt` tree, drop the
   `lidarr-music` PV/PVC and mount the `lidarr-media` claim at
   `/music` with the matching subPath in the values.
2. **qBittorrent's static IP.** Read it from the source of truth —
   the OPNsense policy-routing rule's source address, or
   `ip -4 addr` on the qbittorrent LXC's LAN interface. Replace
   BOTH `203.0.113.1/32` occurrences in `values.production.yaml`
   with that IP as a /32. (The placeholder is TEST-NET-3 —
   unroutable — so an unsubstituted policy fails safe.)
3. **Baseline counts.** From the running LXC app (UI or API with
   the key from `config.xml`): artist count and track-file
   count. Also record the `/config` file count and byte total:
   `find ~/lidarr/config -type f | wc -l` and
   `du -sb ~/lidarr/config`.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (lidarr destination) and
   applied via `playbooks/talos-cluster/argocd-project.yml`.
2. Namespace + media volume:
   `kubectl --context admin@homelab apply -f ansible/kubernetes/apps/lidarr/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/gitops-secrets.yml`
   (lidarr is in its Caddy loop). No app secret playbook exists.

## Staging

Values ship with `replicas: 0` (and the step-0 substitutions made).
Commit `feat(lidarr): stage Batch D migration`, push, register the
Application, approve the first Sync — objects and PVCs appear, no
pod starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/applications/lidarr.yaml
```

Gate: the `lidarr-media` PV is Bound, and the chart claims
(`lidarr-config`, `lidarr-tailscale-state`, `lidarr-caddy-state`)
are provisioned on **k8s-w-1** — the controller is node-pinned,
verify anyway; a claim that lands on k8s-w-2 is the Speedtest
failure mode and stops this app here.

## Cutover

1. Stop the LXC stack:

   ```sh
   ssh root@lidarr 'cd ~ && docker compose down'
   ```

2. Copy the config with a datacopy helper pod mounting the
   `lidarr-config` claim (busybox image as in the LubeLogger
   README): tar-stream `~/lidarr/config` from the LXC into the
   claim, preserving ownership (the app runs as PUID 1000). Verify
   file count AND total bytes against the step-0 baseline.
   Mismatch → debug and re-copy; if a copy will not verify, park
   this app (below) and report.

3. Create the bootstrap Tailscale auth Secret from a one-use
   Headscale pre-auth key — the RomM pipeline verbatim, only the
   namespace and Secret name change:

   ```sh
   ssh root@pangolin 'docker exec headscale headscale preauthkeys create --user 1 --expiration 1h --output json' \
     | jq -sr 'map(select(type == "object" and has("key"))) | last | .key' \
     | tr -d '\r\n' \
     | kubectl --context admin@homelab -n lidarr create secret generic lidarr-tailscale-auth --from-file=TS_AUTHKEY=/dev/stdin
   ```

   Assert before activating: decode the Secret's `TS_AUTHKEY`
   and confirm its length is exactly 64 characters (print the
   count only, never the key). Not 64 → recreate it; do not
   proceed on a bad key.

4. Remove `replicas: 0` from the values, commit
   `feat(lidarr): activate Batch D migration`, push, approve Sync.
   The pod starts on k8s-w-1; verify the new tailnet node
   registered in Headscale, then delete the LXC's stale `lidarr`
   node (list nodes before/after; touch ONLY the node named
   lidarr; no tailscale-acl or policy changes).

5. Repoint the stored connections (the pod cannot resolve tailnet
   names; use the app API with the key from `config.xml`, or the
   UI through the tailnet URL):
   - Download client (qBittorrent): host = the static IP from
     step 0, port 8080, credentials unchanged.
   - Prowlarr indexer entries: host = `prowlarr.prowlarr.svc.cluster.local`,
     port 9696 (the API path and Prowlarr API key are unchanged).
     If Prowlarr has not cut over yet, leave its entries pointing
     at the prowlarr LXC's tailnet name **only if it still
     resolves** — it will not from the pod; expect indexer errors
     until Prowlarr lands, then repoint. (Cutover order in the
     batch prompt puts Prowlarr first for this reason.)

6. Verify, all required:
   - Pod Running on k8s-w-1, all containers Ready, 0 unexpected
     restarts.
   - `https://lidarr.tail.davegallant.ca` answers (302 to the
     login page is correct).
   - Artist and track-file counts match the step-0 baseline.
   - Download-client test in Lidarr passes against the qBittorrent
     LXC.
   - Hardlink proof: pick an already-imported track file under
     `/mnt` and confirm `stat` shows link count ≥ 2 (the download
     and library paths are the same inode) from inside the pod.
   - A Velero backup from the `lidarr-daily` Schedule completes
     WITH Completed PodVolumeBackups for the config volume.

7. Exclude the stopped LXC's playbook from the daily CI run (the
   Batch B mechanism) and record the cutover in a closing docs
   commit.

## Parking and failure rules

Any failed gate parks **this app only**: leave the cluster objects
as they are (deployment back at `replicas: 0` if it was raised),
restart the LXC stack so Lidarr keeps serving there, and report.
**No rollbacks**: do not delete copied data, claims, or cluster
objects, and do not reverse any step on your own initiative —
state-reversing actions are Dave's explicit call, in the moment.
If a step is genuinely ambiguous, stop and ask rather than guess.
The stopped LXC stays in place as the fallback until Dave retires
it.
