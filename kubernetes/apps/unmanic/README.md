# Unmanic

Unmanic is exposed only over the tailnet at `https://unmanic.tail.davegallant.ca`.
It starts with exactly one test directory mounted at `/library`, backed by
`/mnt/pool/tdarr-test` on the Cinema NFS export. The full movies and TV trees are
not mounted. Do not add them until the single-file test is reviewed.

The UI and worker run in one container. Library configuration and plugin state
live on a 2 GiB local-path PVC pinned to `k8s-w-1` and are included in the daily
Velero backup. Worker cache is ephemeral. The NFS media PVC uses `Retain` and is
not part of Velero backups; it exposes only the test directory through a pod
`subPath`. The original movie remains in Jellyfin's library, untouched.

Unmanic requests one Intel GPU share and uses Quick Sync for HEVC encoding.
The Intel GPU device plugin allows two containers per worker GPU for batch
transcoding; this can contend with Jellyfin's real-time transcodes.

No credentials or external Secrets are required. The pod runs as UID/GID 1000,
with a restricted security context and a Cilium policy allowing only tailnet
Gateway ingress, cluster DNS, and NFS to `192.168.1.83:2049`.

Provision `namespace.yaml` and `storage.yaml`, sync the Argo CD Application,
then sync `tailnet-gateway` and `velero-schedules`. Validate the UI at the
tailnet URL and ensure the library path is `/library`. Configure a single
worker and a video conversion plugin only after checking its settings. Start
with the copied *A Bug's Life* file; compare the output before considering any
broader library mount.

To recover settings, restore the `unmanic` Velero backup to a compatible local
volume and schedule the pod onto `k8s-w-1`. The media test copy is outside
Velero. Deleting the app does not remove the NFS files because the PV reclaim
policy is `Retain`.
