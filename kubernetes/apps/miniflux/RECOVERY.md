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
state and choose a recovery point. A selective sync bypasses hooks and does not
record history; it is an emergency mechanism, not an automatic data rollback.
Restoring production data and reconciling Git/Argo requires a deliberate
app-specific procedure and has not yet been automated.

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
