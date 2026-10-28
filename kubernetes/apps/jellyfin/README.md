# Jellyfin

Jellyfin runs as a production Kubernetes workload on `k8s-w-1` with Intel
hardware transcoding. Argo CD manages the chart resources; the namespace and
static read-only media volume are applied separately from
[`storage.yaml`](storage.yaml).

The media claim mounts cinema's mergerfs pool at `/mnt`, preserving the
`/mnt/movies` and `/mnt/tv` paths. Media remains read-only and outside Velero.
The SQLite config uses a 10 GiB local-path PVC on `k8s-w-1`; the disposable
transcode cache uses `emptyDir`.

The existing Pangolin Newt identity is supplied through the externally
provisioned `jellyfin-newt-external` Secret. The Pangolin target is
`jellyfin:8096`, matching the namespace-local Service. Velero backs up the
config volume daily at 05:30 UTC with a 336-hour retention period, excluding
Secrets. Before restoring config, verify SQLite integrity and preserve the
media share separately.
