# Audiobookshelf on the Talos cluster (Argo CD)

Audiobookshelf runs from the bjw-s **app-template** chart (5.3.0) as
an Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/audiobookshelf.yaml`. Syncs are
manual, pruning is off, and deleting the Application preserves the
workload.

Workload source of truth: `playbooks/audiobookshelf/docker-compose.yml`
(image `ghcr.io/advplyr/audiobookshelf:2.37.1`, port 80,
`/mnt/media/Audiobooks:/audiobooks`, `/mnt/media/Podcasts:/podcasts`,
`./metadata:/metadata`, `./config:/config`).

Exposure is **public via Pangolin — this app stays public.** The
compose's Newt sidecar is reproduced in-pod with the *same* Newt
identity, so the existing Pangolin route and public URL carry over
unchanged. Never rewrite this app as tailnet-only.

The libraries are static NFS PVs (`storage.yaml`) onto the existing
TrueNAS exports (`/mnt/tank/media/Audiobooks`,
`/mnt/tank/media/Podcasts`), read-write like the LXC mounts; they
never move and are never Velero-backed-up (TrueNAS snapshots + Drive
sync). Verify the share paths against the LXC's `/mnt/media` mount
sources before applying `storage.yaml`. The app state lands on two
local-path PVCs: `config` (1Gi) and `metadata` (10Gi — cover cache
and backups grow). The image runs as root; copied state keeps its
LXC ownership (no chown to 1000 for this app).

Secrets stay in Vault and outside Argo's ownership:
`audiobookshelf-newt-external`, created by
`playbooks/talos-cluster/audiobookshelf-secret.yml`.

Backups: Velero Schedule `audiobookshelf-daily` (in the values,
opt-in mode) with pod annotation
`backup.velero.io/backup-volumes: config,metadata`. The network
policy is the house default-deny CiliumNetworkPolicy, in the values
as `rawResources.defaultDenyNetworkPolicy`.
