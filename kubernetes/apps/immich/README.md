# Immich production migration

The production LXC remains authoritative until the migration gates pass. The
Kubernetes test instance at `immich-k8s.tail.davegallant.ca` has verified Intel
VAAPI transcoding, and its disposable database and library PVCs are retained.
Do not sync the production values before restoring the fresh database and
stopping the LXC server and ML containers.

The tailnet-only URL is `https://immich-k8s.tail.davegallant.ca`, routed by
the shared tailnet Gateway to the `immich` Service on port 2283. Production
will take over that endpoint when the app is synced. The existing
`https://immich.tail.davegallant.ca` LXC endpoint remains available for
rollback; switch Homepage and Gatus to the Kubernetes URL after the cutover
has passed its health checks.

The planned deployment uses one Recreate pod on k8s-w-2 with Immich server,
CPU ML, Valkey, and Postgres. Its server requests the worker's Intel GPU. This
is a single failure domain; Postgres is in-pod and server/ML cannot scale
independently. Jellyfin uses a different host GPU.

`production-storage.yaml` defines a retained NFS PV for the existing TrueNAS
library and a new annotated local-path PostgreSQL PVC. The NAS export must
allow k8s-w-2 and preserve its existing client, ownership mapping and snapshot
protection. The original LXC and its NFS library must have no running writer
when the Kubernetes server is started. The original library path inside the
container is retained. Postgres never lives on NFS. The local DB PV is tied to
k8s-w-2; losing the node requires recovery from backup.

`immich-production-secret.yml` provisions credentials from Ansible Vault.
`production-restore-pod.yaml` starts only a new empty PostgreSQL against the
production claim. `production-nfs-check.yaml` mounts the NAS library read-only
for the preflight gate; `production-nfs-permission-check.yaml` checks write
permission bits with the pod identity without creating files. These resources
are applied separately from Argo.
The app references only `immich-production-external`; the Secret supplies
`DB_USERNAME`, `DB_PASSWORD`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` without
placing their values in Git.

The production values include a daily 05:10 UTC Velero schedule with a
PostgreSQL logical dump hook and the database volume; Secrets are excluded.
It starts ten minutes after the existing 05:00 UTC Forgejo schedule, whose
latest backup completed in about two minutes. The NAS
library is excluded and depends on its separate snapshot and off-host backup
path. Validate a successful one-off backup, its hook and nonzero completed
PodVolumeBackup before treating the deployment as protected. Confirm the daily
schedule is enabled and verify its first scheduled run separately.

Before cutover, prevent automated LXC reapplication, capture a verified fresh
off-host database backup and NAS snapshot, stop the LXC writers, capture a
final database dump and source counts, restore to the empty target, and
compare exact table counts and source file paths. Stop the restore pod's
PostgreSQL before starting the production deployment. Review the server-side
Argo diff and dry run, sync without prune or force, then verify database,
media, uploads, GPU video processing, backups, and URL identity. Do not delete
any LXC, PVC, data, test resources or registration without separate approval.

If any cutover gate fails, freeze at that step, preserve evidence, and wait for
direction. Do not reverse the writer handoff or restart the LXC writers after
Kubernetes has started without explicit approval. Keep the Kubernetes PVCs
and all backups for diagnosis; do not delete either deployment's data.
