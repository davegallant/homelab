# Jellyfin test instance

This manually synced test uses the same Jellyfin image as LXC 108 and is
reachable only through a port-forward. It has no Gateway or Newt route. The
LXC remains production; do not change its URL or stop it for this test.

The hand-applied `storage.yaml` provides a retained, read-only NFS media
claim from cinema at `192.168.1.83:/mnt/pool`, mounted at `/mnt` to preserve
`/mnt/movies` and `/mnt/tv`. It is not part of Velero. The SQLite config uses
a 10 GiB local-path PVC annotated `volumeType: local` on k8s-w-1. Populate it
from an integrity-checked frozen config before the server's first start.
The cache uses `emptyDir`: transcodes are disposable, and emptyDir keeps
scratch writes off the media share and the persistent SQLite volume.

The container requests 500m CPU, 1 GiB memory and one Intel GPU; limits are
2 CPU, 3 GiB and one GPU. The workload is pinned to k8s-w-1. Cilium permits
cluster DNS, same-namespace traffic and world metadata access, with LAN and
cluster ranges denied. No separate Kubernetes Secret is required for the test;
the copied config contains existing credentials and must remain protected.

This disposable test has no Velero schedule. Before cutover, take a final
frozen config copy, establish and prove a Velero schedule and one-off backup,
decide the Gateway or Newt route, check the API key consumer, plan the LXC
stop order, and prove URL identity. Recovery of a production config needs its
local PVC data and separately protected media; the test copy is not a backup.

## Cutover staging

The production handoff is staged with the existing Pangolin Newt identity in
`jellyfin-newt-external`, provisioned from Vault by
`ansible/playbooks/talos-cluster/jellyfin-secret.yml`. The Newt container is
initially disabled so it cannot connect while the LXC connector is active.
The existing Pangolin target is `jellyfin:8096`; the namespace-local Service
has that name. Enable Newt only after the LXC has stopped and the final frozen
config copy has passed its integrity and file-manifest checks. Verify the
public URL reaches this server before considering the handoff complete.

The staged Velero schedule runs at 05:30 UTC with a 336-hour TTL, excludes
Secrets and backs up only the annotated config volume. Verify the enabled
schedule and a completed one-off backup with a nonzero config PodVolumeBackup
before cutover; the first scheduled backup remains pending until it completes.
Velero copies the running SQLite files without an application quiesce hook;
restore to an isolated location and run SQLite integrity checks before use.
The LXC playbook is excluded from automation and the all-host import when the
staging changes are deployed. The stopped LXC and its data remain recovery
material. Media stays on cinema's separate storage and is not in Velero.
