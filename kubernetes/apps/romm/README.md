# RomM on the Talos cluster (Argo CD)

RomM runs from the bjw-s **app-template** chart (5.3.0) as an Argo CD
Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/romm.yaml`. Syncs are manual,
pruning is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/romm/docker-compose.yml`
(app `docker.io/rommapp/romm:5.4.0`, port 8080; database
`docker.io/mariadb:13.0.2`). The app and MariaDB run in the same pod. Database data uses its own persistent volume; back it up with the Velero schedule defined in the production values.

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

Kubernetes binds its state through static local PVs defined in
`state-local-pv.yaml`. Preserve the worker-local paths during recovery.

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
