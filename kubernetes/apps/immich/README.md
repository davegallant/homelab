# Immich on Kubernetes

Production runs on `k8s-w-2` at the tailnet-only URL
`https://immich.tail.davegallant.ca`, through the shared tailnet Gateway to the
`immich` Service on port 2283. The LXC (104 on
`pve-g3-1`) is stopped and its Proxmox `onboot` setting is disabled. Its
Headscale node was renamed `immich-lxc-retired` and expired; the registration
is retained. Homepage and Gatus use the original hostname.

One Recreate pod contains Immich server, CPU machine learning, Valkey, and
Postgres. The server requests the worker's Intel GPU, and the restored
production configuration uses QSV. This is a single failure domain; Postgres
is in-pod and server/ML cannot scale independently. Jellyfin uses a different
host GPU. Machine learning reuses the local model-cache claim from the test.

`production-storage.yaml` defines a retained NFS PV for the existing TrueNAS
library and an annotated local-path PostgreSQL PVC. The NAS export allows the
original client and `k8s-w-2`; its mapall identity owns the library files.
The original library path inside the server container is retained. Postgres
is local to `k8s-w-2`, not NFS; losing that node requires database recovery.
`immich-production-secret.yml` provisions the production database credentials
from Ansible Vault as the `immich-production-external` Secret.

For backup scope and timing, inspect the production chart and central
[Schedule inventory](../velero-schedules/). Verify a successful PostgreSQL dump
hook and completed nonzero PodVolumeBackup, then rehearse restore. A one-off
backup does not prove scheduled or off-site coverage. Verify NAS library
snapshots, off-site copies and cloud-sync success separately; library data is
excluded from Velero.

The staging manifests `production-nfs-check.yaml` and
`production-nfs-permission-check.yaml` performed the NFS checks. The completed
`production-restore-pod.yaml` was used for the database restore. Do not start
that restore pod against the production claim while the application is running:
it would start a second PostgreSQL on the same data. Use an isolated claim for
future restore rehearsals.

The stopped LXC database is a pre-cutover copy and becomes stale as soon as
Kubernetes accepts changes. Do not restart its writers against the shared
library without an explicitly approved recovery plan and a current database
handoff. Preserve the LXC, PVCs, snapshots, and backup evidence. If a recovery
gate fails, freeze that step and wait for direction; do not reverse the writer
handoff without explicit approval.
