# Sonarr on the Talos cluster (Argo CD)

Sonarr runs from the bjw-s **app-template** chart (5.3.0) as an Argo CD
Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/sonarr.yaml`. Syncs are manual,
pruning is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/sonarr/docker-compose.yml`
(app `docker.io/linuxserver/sonarr:4.0.20`, port 8989). All state is
the `/config` directory (SQLite database, config.xml, logs); there
is no separate database to dump — the cutover is a verified file
copy, and Sonarr's own startup migrations handle the rest.

Exposure is **tailnet-only**: the pod mirrors the RomM shape —
userspace Tailscale sidecar → in-pod Caddy (8443, Cloudflare DNS-01)
→ Sonarr on 127.0.0.1:8989, at `sonarr.tail.davegallant.ca`,
replacing the LXC's host-level `tailnet_caddy` role.

**qBittorrent does not move.** It keeps its LXC, its static LAN IP,
and its OPNsense → Mullvad policy route (Batch D design, Dave,
2026-10-23). This pod reaches the qBittorrent API over the LAN
exactly as the LXC does today; the CiliumNetworkPolicy carries the
single new rule that split requires. The shared media tree is a
static NFS PV (`storage.yaml`) mounted at `/mnt` — the identical
path the LXC uses — so every path in Sonarr's database stays true
and hardlink imports keep working: NFS link/rename are server-side
operations within the export, unaffected by which client asks. The
tree never moves and is never Velero-backed-up (TrueNAS snapshots +
Drive sync).

Secrets stay in Vault and outside Argo's ownership:
`sonarr-caddy-external` from `playbooks/talos-cluster/gitops-secrets.yml`,
and the bootstrap-only one-use `sonarr-tailscale-auth`. There is
deliberately no app Secret: Sonarr's API key and its qBittorrent
credentials live in `config.xml`, which arrives with the copied
`/config`.

Backups: Velero Schedule `sonarr-daily` (in the values) with pod
annotation `backup.velero.io/backup-volumes: config-local`. The network
policy is the house default-deny CiliumNetworkPolicy, in the values
as `rawResources.defaultDenyNetworkPolicy`, plus the qBittorrent
exception described there.

## Step 0 — verify before staging (do not skip)

1. **Media export.** On the sonarr LXC, record what backs `/mnt`:
   `findmnt -no SOURCE,FSTYPE /mnt`. Correct the share in
   `storage.yaml` if it is not the `/mnt/tank/media` export
   (if `/mnt` spans several exports, follow the multi-PV note in
   `storage.yaml` instead). The in-pod `/mnt` tree must be
   identical to the LXC's.
2. **qBittorrent's static IP.** Read it from the source of truth —
   the OPNsense policy-routing rule's source address, or
   `ip -4 addr` on the qbittorrent LXC's LAN interface. Replace
   BOTH `203.0.113.1/32` occurrences in `values.production.yaml`
   with that IP as a /32. (The placeholder is TEST-NET-3 —
   unroutable — so an unsubstituted policy fails safe.)
3. **Baseline counts.** From the running LXC app (UI or API with
   the key from `config.xml`): series count and episode-file
   count. Those API counts are the only baseline gate. Do NOT
   gate on file counts or byte totals of the live tree: `du -sb`
   counts directory entries and the tree keeps changing until
   the stop, so it cannot match a later copy — the 2026-10-23
   run parked all four apps on exactly that mismatch while
   every copy was in fact exact.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (sonarr destination) and
   applied via `playbooks/talos-cluster/argocd-project.yml`.
2. Namespace + media volume:
   `kubectl --context admin@homelab apply -f ansible/kubernetes/apps/sonarr/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/gitops-secrets.yml`
   (sonarr is in its Caddy loop). No app secret playbook exists.

## Staging

Values ship with `replicas: 0` (and the step-0 substitutions made).
Commit `feat(sonarr): stage Batch D migration`, push, register the
Application, approve the first Sync — objects and PVCs appear, no
pod starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/applications/sonarr.yaml
```

Gate: the `sonarr-media` PV is Bound, and the chart claims
(`sonarr-config`, `sonarr-tailscale-state`, `sonarr-caddy-state`)
are provisioned on **k8s-w-1** — the controller is node-pinned,
verify anyway; a claim that lands on k8s-w-2 is the Speedtest
failure mode and stops this app here.

## Cutover

1. Stop the LXC stack:

   ```sh
   ssh root@sonarr 'cd ~ && docker compose down'
   ```

2. Copy the config with a datacopy helper pod mounting the
   `sonarr-config` claim (busybox image as in the LubeLogger
   README): tar-stream `~/sonarr/config` from the LXC into the
   claim, preserving ownership (the app runs as PUID 1000). Verify
   the copy against the FROZEN source, measured identically on
   both sides: per-file path+size lists
   (`find . -type f -printf '%P %s\n' | sort`) must diff empty.
   Mismatch → debug and re-copy; if a copy will not verify, park
   this app (below) and report.

   The app mounts `sonarr-config-local`, a retained Local PV in
   `storage.yaml` on k8s-w-1 that points to the same on-disk config
   directory as the original `sonarr-config` claim. The original
   claim and PV stay retained and are not deleted.

3. Create the bootstrap Tailscale auth Secret from a one-use
   Headscale pre-auth key — the RomM pipeline verbatim, only the
   namespace and Secret name change:

   ```sh
   ssh root@pangolin 'docker exec headscale headscale preauthkeys create --user 1 --expiration 1h --output json' \
     | jq -sr 'map(select(type == "object" and has("key"))) | last | .key' \
     | tr -d '\r\n' \
     | kubectl --context admin@homelab -n sonarr create secret generic sonarr-tailscale-auth --from-file=TS_AUTHKEY=/dev/stdin
   ```

   Assert before activating: the decoded `TS_AUTHKEY` uses the
   modern `hskey-auth-<12-char-prefix>-<64-char-secret>` format
   (88 characters total). Assert the secret component is exactly
   64 characters; print only the count, never the key. Recreate a
   key that fails this check; do not activate with it.

4. Remove `replicas: 0` from the values, commit
   `feat(sonarr): activate Batch D migration`, push, approve Sync.
   The pod starts on k8s-w-1; verify the new tailnet node
   registered in Headscale, then delete the LXC's stale `sonarr`
   node (list nodes before/after; touch ONLY the node named
   sonarr; no tailscale-acl or policy changes).

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
   - `https://sonarr.tail.davegallant.ca` answers (302 to the
     login page is correct).
   - Series and episode-file counts (API) match the step-0 baseline.
   - Download-client test in Sonarr passes against the qBittorrent
     LXC.
   - Hardlink proof: pick an already-imported episode file under
     `/mnt` and confirm `stat` shows link count ≥ 2 (the download
     and library paths are the same inode) from inside the pod.
   - A Velero backup from the `sonarr-daily` Schedule completes
     WITH Completed PodVolumeBackups for the config volume.

7. Exclude the stopped LXC's playbook from the daily CI run (the
   Batch B mechanism) and record the cutover in a closing docs
   commit.

## Parking and failure rules

Any failed gate parks **this app only**: leave the cluster objects
as they are (deployment back at `replicas: 0` if it was raised),
restart the LXC stack so Sonarr keeps serving there, and report.
**No rollbacks**: do not delete copied data, claims, or cluster
objects, and do not reverse any step on your own initiative —
state-reversing actions are Dave's explicit call, in the moment.
If a step is genuinely ambiguous, stop and ask rather than guess.
The stopped LXC stays in place as the fallback until Dave retires
it.

## Batch D execution status (2026-10-23)

Sonarr is **parked**. The Argo Application, claims, and copied config remain
in place with `replicas: 0`; the config PVC is Bound to `k8s-w-1`. The copy
matches the stopped LXC source (744 files, 280,464,293 regular-file bytes).
The saved step-0 baseline was 742 files and 280,764,841 bytes from `du -sb`,
so the baseline gate was not accepted. The runbook's shorthand `/root/config`
source did not exist; the observed source was `/root/sonarr/config`. The LXC
Compose stack was restarted and is serving again. The media source was
corrected to `192.168.1.83:/mnt/pool`, and both qBittorrent policy entries
use `192.168.1.152/32`. No Headscale key or node changes were made.

## Batch D continuation status (2026-10-23)

Fresh API baseline: 67 series and 4,215 episode files. The refreshed config
copy's per-file path+size manifest diff was empty. The first and replacement
bootstrap keys (IDs 65–66) each decoded to 88 characters, failing the required
64-character assertion; neither was used to activate the pod, and both were
explicitly expired. Sonarr remains parked at `replicas: 0` and its LXC Compose
stack is running. No Headscale node was created or deleted.
