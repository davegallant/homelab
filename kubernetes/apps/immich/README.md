# Immich on Kubernetes

Production runs on `k8s-w-2` at the tailnet-only URL
`https://immich-k8s.tail.davegallant.ca`, through the shared tailnet Gateway
to the `immich` Service on port 2283. The LXC (104 on `pve-g3-1`) is stopped
and its Proxmox `onboot` setting is disabled. The requested eventual handoff
of `immich.tail.davegallant.ca` remains pending.
Homepage and Gatus still use the old hostname until that handoff.

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

The 2026-10-28 cutover restored a frozen database dump into a fresh claim.
All 73 public table counts matched the source, including 16,921 asset rows.
The app verified its library mounts and five original photos were read from
the server container; Dave uploaded a photo and confirmed it appeared. A
synthetic QSV encode passed in the production pod.
The previous disposable test PVCs and network policy are retained; their
prune-skipped state makes Argo report `OutOfSync`. Do not prune them as part
of a normal sync.

The production values include a daily 05:10 UTC Velero schedule with a
PostgreSQL logical dump hook and its local database volume; Secrets are
excluded. The one-off `immich-migration-20261028` backup completed with one
successful hook and an 833,210,457-byte completed PodVolumeBackup. The first
scheduled run still needs verification. Velero writes to Garage on TrueNAS;
the Garage cloud sync last reported a Google Drive rate-limit failure, so
off-host protection of that backup is not confirmed.

The NFS library is excluded from Velero. TrueNAS has an enabled daily
recursive snapshot of `tank`, and the frozen cutover snapshot is
`tank/immich@immich-cutover-20261028T025001Z`. No configured TrueNAS cloud
sync was found for `tank/immich`; an off-host library copy has not been
verified. The protected final database dump and table counts are under
`~/.local/share/immich-migration-20261027/` on the operator's machine.

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
