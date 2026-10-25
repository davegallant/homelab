# Kubernetes storage - CANONICAL RULE (read this before adding any volume)

This file is the single source of truth for local storage in this cluster.
It exists because Forgejo's 2026-10-24 migration failed Velero for a reason
that was already documented in three other places (Homepage README,
local-path README, BACKUPS.md) and still got missed: the lesson was
scattered, not checked. If this file and another doc disagree, this file
wins for new work - and the other doc must be fixed to match it.

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
      workload to a worker. w-2 is already tight - do not place a new
      main data volume on w-2 without reporting why. w-1 is the default
      for pinned local data.
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

## Adoption pattern - converting an existing local-path volume in place

The *arr stack (Prowlarr, RomM, 2026-10-23/24) did NOT start on static
local and did NOT move its data to get there. It started on chart-managed
local-path PVCs (hostPath by default), then, to make Velero work, it
re-declared the SAME on-disk directories as static local PVs:

- Prowlarr: static PV `prowlarr-config-local` (pve-g3-1-local, w-1) with
  local path `/var/mnt/local-path/pvc-af67..._prowlarr_prowlarr-config` -
  that path IS the provisioner's directory for the original PVC.
  Values point at `existingClaim: prowlarr-config-local`.
- RomM: static PVs in `apps/romm/state-local-pv.yaml` (storageClass "",
  w-1) with local paths `/var/mnt/local-path/pvc-..._romm_romm-*` -
  again, the provisioner's own directories, re-declared as `local`.
  Comment in that file: 'Kubernetes local volumes are eligible for
  Velero filesystem backups; hostPath volumes from the local-path
  StorageClass are not.'

No data was copied in that conversion - the directory stayed put, only
its volume TYPE changed from hostPath to local, via a new PV/PVC pair
with a new claim name (old claims are rollback material until cutover
passes). Sidecar state that must NOT be backed up (e.g. Prowlarr
tailscale-state, caddy-state) stayed on plain local-path, deliberately
unannotated and excluded from Velero (backup-volumes annotation only
lists the config volume; Tailscale identities are excluded from Velero
by cluster policy).

This adoption pattern is a valid third option for an existing hostPath
volume, alongside (a) a new static PV from scratch (needs a host dir +
possible reboot) and (b) a new local-path PVC with `volumeType: local`
(needs a data re-copy). Choose adoption when the data already sits in
a provisioner directory on the right node and you want no data move and
no reboot - but verify Velero PVBs with nonzero bytes after adoption,
just like any other shape. Do NOT adopt by editing the existing PV in
place: create the new static PV/PVC pair, point values at the new claim,
and leave the old PVC/PV untouched until the new backup is proven.

## Why both shapes exist (and why neither is 'the cleanup')

- Static local came first (Homepage, Kiwix, Miniflux, RomM, *arr). It is
  proven, explicit, and costs a machine-config entry + a node reboot for
  each NEW host directory.
- Local-path provisioner was adopted (2026-10-22) to remove that reboot
  cost for future apps: one base-path `.keep` entry, then per-volume
  directories are created by helper pods. Its default volume type is
  hostPath, which is why the annotation exists and why it must be set.
- Do NOT 'clean up' by migrating all static volumes to local-path:
  that would break Velero for every working app. Do NOT migrate all
  local-path volumes to static either, without an inventory: some
  local-path PVCs are rollback/scratch/disposable (e.g. Audiobookshelf
  read-only rollback mounts, POCs), not live backed-up data. Migrate
  only live, Velero-backed volumes, one app at a time, after the
  current migration passes.

## Where the details live (this file does not duplicate them)

- Local-path provisioner install, base path, reclaim, and smoke test:
  [apps/local-path/README.md](apps/local-path/README.md)
- Velero schedules, restore drills, and backup verification:
  [BACKUPS.md](BACKUPS.md) (including the RomM static-local proof and
  the 'Completed alone is insufficient' rule)
- NFS CSI and NAS protection scope: [apps/nfs-csi/README.md](apps/nfs-csi/README.md)
- Forgejo's storage history (Phase 1 local-path failure, Phase 2 Velero
  zero-PVB proof, static fix, annotation test):
  [apps/forgejo/README.md](apps/forgejo/README.md).

## Lesson record (2026-10-24, Forgejo)

Phase 1 specified `storageClass: local-path` with NO annotation.
Provisioner defaulted to hostPath. Phase 2 Velero backup Completed
with zero PVBs, at 0 replicas, and was correctly stopped - but the
stop was then misread as 'hostPath is the blocker' without first
testing Velero with the pod running, and the fix pivoted to static
(+ a worker reboot gate) without first testing the documented
annotation. Future agents: test the cheap, documented fix FIRST
(annotation + pod-running Velero retry) before converting storage
or requesting a reboot. A reboot is a last resort, not a first step.

PROOF (2026-10-25, Forgejo annotation test): new PVC
forgejo-data-local created with `volumeType: local` before
provisioning, Bound on k8s-w-1, PV type `local` (path
/var/mnt/local-path/pvc-f842..._forgejo_forgejo-data-local, no
hostPath), frozen re-copy 67,420 files diff empty, Forgejo at
1 replica internally, Velero backup forgejo-local-annotation-
20261025 Completed with data PVB 989,859,411 bytes. No reboot,
no static conversion, no data move beyond the re-copy. The
old hostPath helper pod warning in that backup (helper pod
skipped) does not invalidate the new pod's PVB - delete the
helper pod during separately approved cleanup so future backups stop warning on it.
