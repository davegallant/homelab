# Kubernetes storage - CANONICAL RULE (read this before adding any volume)

## The reconciled rule

Velero-compatible local storage means ONE of these two shapes, nothing else,
for any volume that must be backed up by Velero. Dave's stated preference
(2026-10-24) is the point of this file: **Velero backups AND new PVs
without reboots.** That is shape (2) below, and it is the DEFAULT for
any NEW volume. Shape (1) is for adoption of an existing directory, or
as a fallback if shape (2) is proven to fail - never as the first step
for a new volume, and never with a reboot unless Dave approves it after
shape (2) has failed.

1. **Static local PV** - hand-written PV + PVC, storageClass
   `pve-g3-1-local`, type `local` (NOT `hostPath`), explicit node pinning
   (usually k8s-w-1), reclaim Retain, host path under /var/mnt/<app>/.
   Proven by Homepage, RomM, *arr. Use this for adoption of an existing
   directory or when the dynamic option has been proven unsuitable.

2. **Dynamic local-path PVC with `volumeType: local`** - storageClass
   `local-path`, PVC metadata.annotations `volumeType: local`, provisioned
   by Rancher local-path-provisioner v0.0.31. This is the dynamic
   alternative, adopted to avoid a machine-config reboot per new volume.
   It is Velero-compatible ONLY with that annotation, and ONLY if the
   backup is proven (see below). Without the annotation, the provisioner
   defaults to `hostPath`, which Velero does NOT support for filesystem
   backups.

**NEVER use these for Velero-backed data:**
- Dynamic local-path PVC with NO annotation (defaults to hostPath).
- Any direct `hostPath` volume in a pod spec.
- NFS for SQLite databases (locking risk - see below).

## The exact annotation (do not guess it)

```yaml
metadata:
  annotations:
    volumeType: local
```

On a PVC using storageClass `local-path`, provisioner
`rancher.io/local-path`. A StorageClass annotation `defaultVolumeType`
can set the default for all volumes on that class, but a PVC annotation
supersedes it. If neither is set, the default is `hostPath`.

**An annotation on an EXISTING hostPath PVC does NOT convert it.**
Existing hostPath PVs must be replaced or copied into a `local` PV/PVC.
Changing a StorageClass default does not convert existing volumes.
A new PVC name is required for a replacement (the old claim name is
occupied until the old PVC is deleted, and old PVCs are rollback
material until cutover passes - do NOT delete them to make room).

## Checklist - every new stateful app MUST pass all of these before sync

- [ ] Daily backup coverage is defined in the app's tracked chart or production
      values, including every namespace holding required state (including a
      companion runner's registration Secret when it cannot be recreated from
      Vault). Copy the existing `336h` TTL and choose a UTC slot after checking
      current schedules and backup durations. Record any Secrets inclusion
      explicitly: Velero resource archives are not encrypted. For data protected
      outside Velero, document the protection and recovery path instead.
- [ ] After deployment, verify the schedule is Enabled, unpaused, covers the
      intended namespaces and resources, and has a sane next UTC run. Record
      the first scheduled backup as pending until it completes; verify its
      required data volumes have Completed PodVolumeBackups with nonzero bytes.
      A successful one-off backup proves volume support, not daily coverage.
- [ ] Volume shape is (1) static local OR (2) local-path + `volumeType: local`.
      If it is neither, STOP - do not sync, do not work around it with a waiver.
- [ ] If static local: host directory under /var/mnt/<app>/ exists on the
      pinned node BEFORE the PV binds. Kubelet will NOT create a missing
      local path. If creating it needs a Talos machine-config patch +
      node reboot, get Dave's approval for the reboot FIRST - a worker
      reboot takes pinned workloads down, it is not a silent step.
- [ ] If dynamic local-path: the PVC was created WITH the annotation,
      and the provisioned PV's type was verified verbatim (kubectl get pv
      -o yaml) as `local`, not `hostPath`, BEFORE any data copy.
- [ ] Node pinning is explicit and intentional. Local volumes bind a
      workload to a worker. Check live disk capacity, inode availability and workload requests
      before choosing a worker.
- [ ] SQLite rule: SQLite databases (Forgejo, etc.) live on LOCAL storage
      only, never NFS. NFS is for media/libraries and other data with a
      separate NAS protection path (TrueNAS snapshots + Drive sync),
      never for a live SQLite file.
- [ ] Velero proof, in this order: (a) pod RUNNING and mounting the volume,
      (b) fresh Velero backup for the namespace, (c) backup phase Completed
      AND PodVolumeBackups present WITH nonzero bytes. Phase Completed
      alone is insufficient - a manifests-only backup with zero PVBs is
      a FAILED backup gate, not a passed one. A backup at 0 replicas has
      no pod volumes to back up, so zero PVBs in that state proves nothing
      about the volume type - do not waive a gate on a 0-replica backup.
- [ ] Data copy proof (for migrations): frozen source manifest, per-file
      path+size lists, diff empty. Do NOT gate a frozen copy against a
      live-tree `du` - the live tree mutates, a mismatch is guaranteed.

## Adopting existing directories

An existing provisioner directory can be referenced by a new static `local`
PV/PVC pair without moving its data. Do not edit the existing PV type in place.
Switch the workload to the new claim and retain old claims until backup and
cutover gates pass. Check for overlapping references before deleting either
claim or its on-disk directory.

## Related operations

- [Provisioner verification](apps/local-path/README.md)
- [Backups and restore drills](BACKUPS.md)
- [NFS CSI](apps/nfs-csi/README.md)
