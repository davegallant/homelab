# Prowlarr on the Talos cluster (Argo CD)

Prowlarr runs from the bjw-s **app-template** chart (5.3.0) as an
Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/prowlarr.yaml`. Syncs are
manual, pruning is off, and deleting the Application preserves the
workload.

Workload source of truth: `values.production.yaml`
(app `docker.io/linuxserver/prowlarr:2.6.5`, port 9696;
Flaresolverr `ghcr.io/flaresolverr/flaresolverr:v3.5.2`). All
state is the `/config` directory (SQLite database, config.xml);
there is no separate database to dump — the cutover is a verified
file copy.

Exposure is **tailnet-only**: the pod mirrors the RomM shape —
userspace Tailscale sidecar → in-pod Caddy (8443, Cloudflare
DNS-01) → Prowlarr on 127.0.0.1:9696, at
`prowlarr.tail.davegallant.ca`, replacing the LXC's host-level
`tailnet_caddy` role.

Flaresolverr moves in-pod as a second app container, reachable at
127.0.0.1:8191. Prowlarr has no media mounts and never talks to
qBittorrent. It cuts over **first** in Batch D so the *arr apps can
repoint their indexer URLs at its cluster Service as they land;
Prowlarr's own connections *to* the apps are repointed at batch
close (step 6), once the apps exist as Services.

Secrets stay in Vault and outside Argo's ownership:
`prowlarr-caddy-external` from `playbooks/talos-cluster/gitops-secrets.yml`,
and the bootstrap-only one-use `prowlarr-tailscale-auth`. There is
deliberately no app Secret: Prowlarr's API key and its indexer/app
credentials live in its config, which arrives with the copied
`/config`.

Backups: Velero Schedule `prowlarr-daily` (in the values) with pod
annotation `backup.velero.io/backup-volumes: config-local`. The network
policy is the house default-deny CiliumNetworkPolicy, in the
values as `rawResources.defaultDenyNetworkPolicy`, extended with
two-way API access between Prowlarr and the three app namespaces.

## Step 0 — verify before staging (do not skip)

**Baseline counts.** From the running LXC app (UI or API with the
key from `config.xml`): indexer count (total and enabled) and the
configured application count. Those API counts are the only
baseline gate. Do NOT gate on file counts or byte totals of the
live tree: `du -sb` counts directory entries and the tree keeps
changing until the stop, so it cannot match a later copy — the
2026-10-23 run parked all four apps on exactly that mismatch
while every copy was in fact exact. (Prowlarr's compose mounts
`~/config` — not `~/prowlarr/config`.)

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (prowlarr destination) and
   applied via `playbooks/talos-cluster/argocd-project.yml`.
2. Namespace:
   `kubectl --context admin@homelab apply -f ansible/kubernetes/apps/prowlarr/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/gitops-secrets.yml`
   (prowlarr is in its Caddy loop). No app secret playbook exists.

## Staging

Values ship with `replicas: 0`. Commit
`feat(prowlarr): stage Batch D migration`, push, register the
Application, approve the first Sync — objects and PVCs appear, no
pod starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/applications/prowlarr.yaml
```

Gate: the chart claims (`prowlarr-config`,
`prowlarr-tailscale-state`, `prowlarr-caddy-state`) are
provisioned on **k8s-w-1** — the controller is node-pinned,
verify anyway; a claim that lands on k8s-w-2 is the Speedtest
failure mode and stops this app here.

## Cutover

1. Stop the LXC stack:

   ```sh
   ssh root@prowlarr 'cd ~ && docker compose down'
   ```

2. Copy the config with a datacopy helper pod mounting the
   `prowlarr-config` claim (busybox image as in the LubeLogger
   README): tar-stream `~/config` from the LXC into the claim,
   preserving ownership (the app runs as PUID 1000). Verify the
   copy against the FROZEN source, measured identically on both
   sides: per-file path+size lists
   (`find . -type f -printf '%P %s\n' | sort`) must diff empty.
   Mismatch → debug and re-copy; if a copy will not verify, park
   this app (below) and report.

   The app mounts `prowlarr-config-local`, a retained Local PV in
   `storage.yaml` on k8s-w-1 that points to the same on-disk config
   directory as the original `prowlarr-config` claim. The original
   claim and PV stay retained and are not deleted.

3. Create the bootstrap Tailscale auth Secret from a one-use
   Headscale pre-auth key — the RomM pipeline verbatim, only the
   namespace and Secret name change:

   ```sh
   ssh root@pangolin 'docker exec headscale headscale preauthkeys create --user 1 --expiration 1h --output json' \
     | jq -sr 'map(select(type == "object" and has("key"))) | last | .key' \
     | tr -d '\r\n' \
     | kubectl --context admin@homelab -n prowlarr create secret generic prowlarr-tailscale-auth --from-file=TS_AUTHKEY=/dev/stdin
   ```

   Assert before activating: the decoded `TS_AUTHKEY` uses the
   modern `hskey-auth-<12-char-prefix>-<64-char-secret>` format
   (88 characters total). Assert the secret component is exactly
   64 characters; print only the count, never the key. Recreate a
   key that fails this check; do not activate with it.

4. Remove `replicas: 0` from the values, commit
   `feat(prowlarr): activate Batch D migration`, push, approve
   Sync. The pod starts on k8s-w-1; verify the new tailnet node
   registered in Headscale, then delete the LXC's stale `prowlarr`
   node (list nodes before/after; touch ONLY the node named
   prowlarr; no tailscale-acl or policy changes).

5. Repoint the Flaresolverr URL (the pod cannot resolve the
   compose service name): Prowlarr → Settings → Indexers →
   Flaresolverr host = `http://127.0.0.1:8191` (API or UI).

6. **Batch-close step** (once sonarr, radarr and lidarr have cut
   over): repoint Prowlarr's application connections to the
   cluster Services — `sonarr.sonarr.svc.cluster.local:8989`,
   `radarr.radarr.svc.cluster.local:7878`,
   `lidarr.lidarr.svc.cluster.local:8686` — API keys unchanged,
   then run each application's Test in Prowlarr. Until then the
   app connections are expected to fail (the stored tailnet names
   do not resolve from the pod); indexer operation is unaffected.

7. Verify, all required (step 6's app tests are the batch-close
   gate, verified then):
   - Pod Running on k8s-w-1, all containers Ready (including
     flaresolverr), 0 unexpected restarts.
   - `https://prowlarr.tail.davegallant.ca` answers (302 to the
     login page is correct).
   - Indexer count (API) matches the step-0 baseline, and a search or
     Test against at least one Flaresolverr-backed indexer and
     one plain indexer returns results.
   - A Velero backup from the `prowlarr-daily` Schedule completes
     WITH Completed PodVolumeBackups for the config volume.

8. Exclude the stopped LXC's playbook from the daily CI run (the
   Batch B mechanism) and record the cutover in a closing docs
   commit.

## Parking and failure rules

Any failed gate parks **this app only**: leave the cluster objects
as they are (deployment back at `replicas: 0` if it was raised),
restart the LXC stack so Prowlarr keeps serving there, and
report. **No rollbacks**: do not delete copied data, claims, or
cluster objects, and do not reverse any step on your own
initiative — state-reversing actions are Dave's explicit call, in
the moment. If a step is genuinely ambiguous, stop and ask rather
than guess. The stopped LXC stays in place as the fallback until
Dave retires it.

## Batch D migration status (2026-10-23)

Prowlarr is **landed on Kubernetes**. Its pod is 4/4 Ready on k8s-w-1 with
zero restarts; the tailnet URL returns HTTP 302. The fresh API baseline matches:
8 indexers (8 enabled) and 3 application connections. The frozen-source path+size
manifest diff was empty. Prowlarr application tests for Sonarr, Radarr, and
Lidarr pass. Velero backup `prowlarr-daily-20261023203342` is Completed, with
the `config-local` PodVolumeBackup Completed.

The media apps' qBittorrent test is the remaining batch gate. The saved host
still resolves to `qbittorrent.tail.davegallant.ca:443` from their pods. The
qBittorrent Compose file publishes its WebUI only on `127.0.0.1:8080`, so the
required LAN endpoint cannot answer without a qBittorrent LXC bind/firewall
change. qBittorrent was not modified.
