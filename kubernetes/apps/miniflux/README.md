# Miniflux on Talos Kubernetes

## Current operations

Argo CD manages the production resources. Follow [release management](../argocd/MANAGEMENT.md)
for updates, external Secrets, and recovery. Use the tracked production values
and Application definition for desired state. Do not run Helm mutations against
resources owned by Argo CD.

The procedures below retain bootstrap and migration context. Check ownership
and current production configuration before using a historical install,
cutover, adoption, or rollback command.

## Bootstrap and migration reference

Migration #5 — the first workload with a real database. Everything
before this was stateless, read-only, or config-only; Miniflux's
Postgres is live state, so this migration is where the backup design
has to grow up: filesystem backup of the data volume PLUS a logical
dump inside every backup.

## Source of truth (LXC, pre-migration)

- Host `miniflux`, Compose at `/root/docker-compose.yml` on the host.
- `miniflux/miniflux:2.3.4` + `postgres:18.6` + Newt 1.19.0 (public
  via Pangolin), all digest-pinned — the chart carries the same pins.
- Database lives in the named Docker volume `miniflux-db` mounted at
  `/var/lib/postgresql`; the app gets `DATABASE_URL`,
  `RUN_MIGRATIONS=1`, `CREATE_ADMIN=1`, admin credentials and
  `BASE_URL` from Vault/group_vars. Every one of those variables
  already exists — this migration adds **no new Vault vars**.

## Design

- **Database:** StatefulSet `miniflux-db` (single replica) on a
  static local PV at k8s-w-1 (`storage.yaml`, `/var/mnt/miniflux/postgres`,
  2 GiB) — Postgres stays off NFS. The directory arrives via a .keep
  entry in `cluster/worker.patch.yaml.j2`; machine config only
  materializes it on node **reboot**, so k8s-w-1 needs a reboot after
  the patch converges, before staging can mount it.
- **App:** Deployment `miniflux`, `DATABASE_URL` assembled from
  Secret-backed env (same credentials as the LXC — a restored or
  re-created database therefore always matches the app), Newt sidecar
  gated on `newt.enabled` exactly like SearXNG/BentoPDF.
- **Backups (the new part):** schedule `miniflux-daily` is opt-in
  only; the database pod annotates its `data` volume into filesystem
  backup and carries a Velero **pre-backup hook**:
  `pg_dump -U <user> -d miniflux > /var/lib/postgresql/dump.sql`.
  Each backup therefore holds the raw volume *and* a logical dump at
  its root. Restore order of preference: (1) restore the volume and
  let Postgres crash-recover, (2) if the data directory is not
  trustworthy, initialize empty and load `dump.sql`. Secrets are
  excluded from backups and re-created from Vault.
- **Data transfer at cutover:** stop the LXC app (the database stays
  up), `pg_dump` from the LXC database to a protected temp file on
  the controller, drop/recreate the cluster database, load the dump,
  then flip Newt on and verify the public URL. The LXC database is
  never written to by the transfer — rollback is simply restarting
  the LXC stack. Note the escape-hatch limit: reads/stars recorded in
  the cluster after cutover do not flow back to the LXC database.

## Verification

- Stage: app answers `/healthcheck` (200) over a port-forward against
  the *empty* cluster database, migrations applied, admin login page
  renders.
- Cutover: row counts for the core tables (`users`, `feeds`,
  `entries`) match between the LXC dump source and the cluster
  database after load; the public base URL serves 200 + Miniflux
  content; a triggered `miniflux-daily` backup Completes with
  **exactly one** completed PodVolumeBackup (the database volume)
  and the hook's `dump.sql` present at the volume root.

## Run order

1. Converge the cluster config patch (.keep entry) and reboot
   k8s-w-1 on Dave's approval.
2. `miniflux.yml` stage → verify.
3. `miniflux.yml` cutover on Dave's go; rollback restarts the LXC
   stack and disables Newt in the cluster.
