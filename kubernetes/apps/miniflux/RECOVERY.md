# Miniflux backup recovery

The daily Miniflux Schedule runs at 03:40 and 15:40 UTC. It backs up the
PostgreSQL local PVC and runs a logical dump hook; Secrets come from Ansible
Vault. A Velero `Completed` phase alone is not proof: check that the backup's
`miniflux-postgres` PodVolumeBackup completed with nonzero bytes and that the
Miniflux dump hook ran successfully. Keep the corresponding application
revision and its pinned PostgreSQL image with a pre-sync backup.

A full Argo sync with the pre-sync gate enabled stops if the last successful
revision does not match live resources. After a partial failed sync, do not
repeatedly retry the full sync. Preserve the backup, inspect the actual live
state and choose a recovery point. A selective sync bypasses the pre-sync hooks,
so neither the gate nor its recovery-history update runs; it does not restore
database data or provide automatic data rollback. Use it only as an emergency
deployment action, with the implications understood. Production data rollback
and Git/Argo reconciliation remain unimplemented and must be handled manually
with an app-specific recovery plan.
The isolated restore drill below validates a recovery point; it is not a
production rollback procedure.

List candidate pre-sync recovery points with:

```sh
just presync-points miniflux
```

The list shows backup name, previous revision and expiry. Entries are
candidates, not proof the gate passed or that a restore will work; verify the
volume, dump hook and revision before using one.

## Isolated logical restore drill

On 2026-11-02, backup `miniflux-presync-preparation-20261102` was restored into
an isolated namespace with a new local-path PVC, without the Miniflux frontend
or Newt sidecar. Velero reported Completed, zero errors and a Completed
PodVolumeRestore of 649306439 bytes. The restored PostgreSQL pod authenticated
over TCP using a recreated credential. Its `dump.sql` loaded with
`ON_ERROR_STOP` into a fresh `template0` database; the restored data contained
one user, 4092 entries and one schema-version row, matching production at the
check. The pinned Miniflux 2.3.4 image started against that logical restore and
its `/healthcheck` returned HTTP 200. The drill namespace and its separate PV
were removed afterward; the production PVC remained bound to its original PV.

On 2026-11-02, the first real pre-sync run created `presync-miniflux-srb6v`
before syncing revision
[`209436ed`](https://github.com/davegallant/homelab/commit/209436ed3ae07341aa2a51a590991b533b39ce6c).
The backup recorded previous revision
[`cc11b088`](https://github.com/davegallant/homelab/commit/cc11b088a112c4e34dac27716a7756a18c1c5b48),
completed without errors, and its PodVolumeBackup covered the exact bound
`miniflux-postgres` claim and `data` volume with 643708366 bytes. The dump hook
completed. The backup was restored into an isolated namespace with a new
local-path PVC; its PodVolumeRestore completed with the same byte count. The
restored DB authenticated over TCP with the Vault-backed DB credentials, and
the 140734213-byte `dump.sql` loaded into a fresh `template0` database with
`ON_ERROR_STOP`. That database contained one user, 24 feeds, 3997 entries and
one schema-version row. Velero completed the isolated restore in 45 seconds.
The drill namespace and PV were removed afterward; the production PVC remained
bound to its original PV. This validates the exact pre-sync backup and its
logical dump. The separate drill above validates Miniflux application startup
against a restored database.

For another drill, first inspect the selected backup's resource inventory and
pod labels: do not restore identity-bearing sidecars or routes. Create a new
namespace with restricted Pod Security and default-deny network isolation;
recreate only the DB credential keys from Vault. Never point the restored PVC
at the production PV. Confirm worker capacity and inode headroom. Use a Velero
resource modifier with a **merge patch**, so it works even when Velero removes
all original PVC annotations:

```yaml
version: v1
resourceModifierRules:
  - conditions:
      groupResource: persistentvolumeclaims
      resourceNameRegex: '^miniflux-postgres$'
      namespaces: [miniflux]
    mergePatches:
      - patchData: |
          {"metadata":{"annotations":{"volumeType":"local"}},"spec":{"volumeName":null,"storageClassName":"local-path"}}
  - conditions:
      groupResource: statefulsets.apps
      resourceNameRegex: '^miniflux-db$'
      namespaces: [miniflux]
    patches:
      - operation: remove
        path: /metadata/annotations/argocd.argoproj.io~1tracking-id
```

Restore the database StatefulSet, its Pod, PVC and PV resources with namespace
mapping and `--include-cluster-resources=false`; ensure the selector cannot
include the frontend Pod or other identity-bearing Pods. Verify the new PVC
uses `local-path`, its PV is `local`, its claim points to the drill namespace,
and its path is under `/var/mnt/local-path/` **before proceeding**. Require a
Completed restore, a Completed nonzero PodVolumeRestore, and a Running database
pod. Authenticate to PostgreSQL over TCP, restore the nonempty `dump.sql`
into a fresh database with `psql -v ON_ERROR_STOP=1`, and verify schema and data.
Run the matching application image against that database without Newt or public
routes, and check its health endpoint. A PVC restore or database socket check
alone does not prove application recovery.

After a successful drill, stop its consumers, verify the drill PV's claim,
storage class and path, then follow the cleanup safeguards in
[BACKUPS.md](../../BACKUPS.md). On a failed gate, freeze the step and retain
evidence; do not delete or modify the failed drill without explicit approval.
