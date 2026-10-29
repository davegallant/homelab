# Local-path provisioner

Read [storage rules](../../STORAGE.md) before creating a volume. The install
playbook and cluster variables own image pins, base path and StorageClass
settings; do not maintain a second inventory here.

The persistent base directory must exist before helper pods create volume
subdirectories. New volumes do not require per-volume machine-config entries.
Retain-policy deletion leaves data on disk; cleanup is a separate decision.
PVC request increases do not enforce directory quotas or grow a filesystem.

## Verification

Run the `local-path.yml` playbook with `local_path_action=smoke`. It uses a
throwaway Delete-policy StorageClass, writes a marker, reads it from a second
pod, and verifies cleanup. This proves provisioning and persistence, not
Velero compatibility; use the backup gate in the storage rules for that.
