# RomM on the Talos cluster (Argo CD)

RomM runs from the bjw-s **app-template** chart (5.3.0) as an Argo CD
Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/romm.yaml`. Syncs are manual,
pruning is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/romm/docker-compose.yml`
(app `docker.io/rommapp/romm:5.4.0`, port 8080; database
`docker.io/mariadb:13.0.2`). The compose **does** bring a database —
confirmed, not optional — so this cutover follows the Miniflux
pattern: in-pod MariaDB as a second container, logical dump/restore,
exact per-table row-count proof. Never raw-copy the MariaDB data
directory.

Exposure is **tailnet-only**: the pod mirrors the Kiwix shape —
userspace Tailscale sidecar → in-pod Caddy (8443, Cloudflare DNS-01)
→ RomM on 127.0.0.1:8080, at `romm.tail.davegallant.ca`, replacing
the LXC's host-level `tailnet_caddy` role.

The library is a static NFS PV (`storage.yaml`) onto the existing
TrueNAS export (`/mnt/tank/media/romm`), read-write like the LXC
mount; `/romm/assets` is the same claim mounted with
`subPath: assets` (the LXC's separate `/mnt/media/romm/assets`
mount). It never moves and is never Velero-backed-up (TrueNAS
snapshots + Drive sync). Verify the share path against the LXC's
mount source before applying `storage.yaml`.

LXC source state: `config` (`~/config` on the LXC),
`resources` and `redis-data` (the compose's named volumes), and
`mysql-data` for MariaDB. Volume names below assume the compose
project prefix from the LXC (compose file in `/root`); confirm with
`docker volume ls` on the LXC first and adjust.

Kubernetes binds the copied state through static local PVs defined in
`state-local-pv.yaml`. The app mounts the `*-local` claims; the original
local-path claims remain read-only at rollback paths for Argo ownership.

Secrets stay in Vault and outside Argo's ownership: `romm-external`
(DB + auth + IGDB keys) from `playbooks/talos-cluster/romm-secret.yml`,
`romm-caddy-external` from `gitops-secrets.yml`, and the
bootstrap-only one-use `romm-tailscale-auth`.

Backups: Velero Schedule `romm-daily` (in the values, opt-in mode)
with pod annotation
`backup.velero.io/backup-volumes: mysql-data-local,config-local,resources-local,redis-data-local`
plus a pre-backup hook that writes a `mariadb-dump` of the `romm`
database into the database volume, so the filesystem backup carries
a consistent logical copy. The network policy is the house
default-deny CiliumNetworkPolicy, in the values as
`rawResources.defaultDenyNetworkPolicy`.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (romm destination;
   `cilium.io`/`CiliumNetworkPolicy` in the namespace resource
   whitelist) and applied via
   `playbooks/talos-cluster/argocd-project.yml` — see the note in
   the Navidrome README.
2. Namespace + library volume:
   `kubectl --context admin@homelab apply -f kubernetes/apps/romm/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/gitops-secrets.yml`
   (romm is in its Caddy loop) and
   `playbooks/talos-cluster/romm-secret.yml`.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and PVCs appear, no pod
starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f kubernetes/apps/argocd/applications/romm.yaml
```

Verify the `romm-library` PV is Bound and the library is visible
from a debug pod before scheduling the cutover.

## Cutover

1. Quiesce and dump the database on the LXC. Stop only the app
   container, capture the per-table row counts (the proof baseline),
   then take a consistent dump:

   ```sh
   ssh root@romm 'cd ~ && docker compose stop romm'
   ssh root@romm 'docker exec romm-db mariadb -u root -p"$MARIADB_ROOT_PASSWORD" -N -e "
     SELECT table_name, table_rows FROM information_schema.tables
     WHERE table_schema = '\''romm'\'' ORDER BY table_name"' \
     > ~/romm-counts-lxc.txt   # run on the Mac side of the ssh instead if env differs
   ssh root@romm 'docker exec romm-db mariadb-dump --single-transaction -u root -p"$MARIADB_ROOT_PASSWORD" romm' \
     > ~/romm-dump.sql
   ```

   (If `MARIADB_ROOT_PASSWORD` is not in the LXC shell's
   environment, read it from the rendered compose on the LXC —
   never print it into logs or this repo.)
   `information_schema` row counts are estimates for some engines;
   for the exact proof, count the tables that matter (platform,
   roms, users, saves, states, firmware, collections) with
   `SELECT COUNT(*)` on both sides and compare those.

2. Stop the rest of the LXC stack:

   ```sh
   ssh root@romm 'cd ~ && docker compose down'
   ```

3. Copy the file state with a datacopy helper pod mounting the
   `config`, `resources`, `redis-data`, and `mysql-data` claims
   (busybox image as in the LubeLogger README): tar-stream
   `~/config` and the `romm_resources` / `romm_redis_data` docker
   volumes from the LXC into their claims, verify file count AND
   total bytes per claim against the LXC sources, and copy
   `romm-dump.sql` into the `mysql-data` claim as `restore.sql`.
   The MariaDB claim starts otherwise EMPTY — the database arrives
   by restore in step 5, not by file copy. Preserve ownership as
   copied (the images run as root). Mismatch → debug and re-copy;
   if a copy will not verify, restart the LXC stack, leave RomM
   serving there, and report.

   Then bind the copied directories through repo-managed static
   local PVs (the Batch A post-cutover shape, following
   `seerr/config-local-pv.yaml`) in a follow-up commit. The
   `state-local-pv.yaml` manifest binds the `*-local` claims; the
   original local-path claims remain declared on read-only paths for
   Argo ownership.

4. **Dave gate — the only one.** Retire the LXC's tailnet node on
   the Headscale host (`headscale nodes delete --identifier
   <old-romm-id>`), then create the one-use preauth Secret without
   printing its value:

   ```sh
   ssh root@pangolin 'docker exec headscale headscale preauthkeys create --user 1 --expiration 1h --output json' \
     | jq -sr 'map(select(type == "object" and has("key"))) | last | .key' \
     | tr -d '\r\n' \
     | kubectl --context admin@homelab -n romm create secret generic romm-tailscale-auth --from-file=TS_AUTHKEY=/dev/stdin
   ```

5. Remove `replicas: 0` from the values, commit, push, approve
   Sync. The pod starts; MariaDB initializes an empty `romm`
   database; the app may error against it briefly — expected.
   As soon as MariaDB accepts connections, restore and restart:

   ```sh
   kubectl --context admin@homelab -n romm exec deploy/romm -c db -- \
     sh -c 'mariadb -u root -p"$MARIADB_ROOT_PASSWORD" romm < /var/lib/mysql/restore.sql'
   kubectl --context admin@homelab -n romm delete pod -l app.kubernetes.io/instance=romm
   ```

   Verify the row counts from step 1 against the restored database
   (same queries, in-cluster). Mismatch → do not declare success;
   the LXC is untouched and remains the rollback target.
   Then delete `restore.sql` from the claim (it is a full database
   copy; it must not ride along in backups):

   ```sh
   kubectl --context admin@homelab -n romm exec deploy/romm -c db -- rm /var/lib/mysql/restore.sql
   ```

6. Verify: pod `4/4` Ready; `https://romm.tail.davegallant.ca`
   shows the existing platforms, ROMs, and users; a scan/fetch
   against IGDB succeeds (world egress); Argo Synced/Healthy.
   Delete the spent `romm-tailscale-auth` Secret. Create and verify
   a Velero backup from schedule `romm-daily` whose PodVolumeBackups
   cover `mysql-data-local`, `config-local`, `resources-local`, and
   `redis-data-local`, all Completed (adapt the script in the
   Navidrome README: schedule label `romm-daily`, expect four
   PodVolumeBackups).
7. Leave the stopped LXC as rollback target until soak completes.

Rollback: the LXC's database was only ever read (dump), never
modified — `docker compose up -d` on the LXC restores service as it
was (re-register its tailscale node first if step 4 already deleted
it); bring the cluster pod down via a `replicas: 0` commit + Sync to
free the tailnet name.
