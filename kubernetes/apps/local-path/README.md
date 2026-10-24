# local-path-provisioner (dynamic node-local storage)

Why this exists: the static local PV pattern (hand-written PV +
machine-config `.keep` entry per app) makes every new stateful app
cost a node reboot, because Talos only writes `machine.files` at
boot. Node-local volumes now come from Rancher's
local-path-provisioner: a workload ships a PVC against the
`local-path` StorageClass, the provisioner's helper pod creates the
directory on the node the pod lands on, and no machine config or
reboot is involved — for any future app, planned or not.

## Decisions baked in

- **Upstream install, pinned.** The provisioner ships as a single
  manifest (its actual distribution mechanism — k3s bundles the
  same). The playbook fetches the pinned tag's manifest, verifies
  its mandatory sha256 in `vars.yaml`, overrides the provisioner and
  helper images with version-and-digest pins, and applies it. Upstream
  also ships a Helm chart; the current install retains manifest ownership.
- **Base path `/var/mnt/local-path`** (patched into the
  provisioner's ConfigMap in place — only the `config.json` key's
  nodePathMap, so upstream's setup/teardown scripts and helper-pod
  template survive untouched). Upstream's default `/opt/...` sits on
  Talos's root filesystem; `/var` is the persistent EPHEMERAL
  partition, the same filesystem as the existing `/var/mnt/<app>`
  static PVs.
- **The base path itself is pre-created** by a single machine-config
  `.keep` entry (`/var/mnt/local-path/.keep` in the worker patch) —
  the one directory the provisioner ever needs from machine config.
  Talos's kubelet cannot create a missing hostPath directory under
  `/var/mnt` (its mkdir hits a read-only filesystem view; observed
  2026-10-22), while pre-created directories bind-mount and take
  writes without trouble — which is why the static PVs always
  worked. Per-volume subdirectories under the base are created by
  the helper pods at provision time; those need no machine config.
- **reclaimPolicy Retain.** Upstream defaults to Delete. Here,
  deleting a PVC releases the PV and leaves the directory on the
  node; data removal is a separate, explicit, human act. The
  StorageClass object is replaced only when its immutable settings differ.
  Matching installs apply it without deleting it. PVC request increases
  follow upstream's allowance but do not resize a filesystem or update
  reported PV/PVC capacity; directory sizes are not enforced.
- **Privileged Pod Security is scoped to `local-path-storage`**
  (the helper pods run privileged with host paths by design). No
  other namespace changes.
- **Coexistence:** the existing static PVs (`pve-g3-1-local`:
  Homepage, Kiwix sidecars, Miniflux) are untouched and stay the
  right choice for volumes that already exist. New stateful apps
  use `local-path`; a chart's storage.yaml shrinks to nothing for
  local data — the PVC goes in the chart with
  `storageClassName: local-path`.
- **Velero compatibility:** local-path-provisioner defaults to
  `hostPath` volumes. Velero filesystem backups do not support
  `hostPath`; they support Kubernetes `local` PVs. For a dynamically
  provisioned PVC that needs Velero filesystem backup, set the
  `volumeType: local` PVC annotation before provisioning it. Existing
  `hostPath` PVs must be replaced or copied into `local` PVs; changing
  the StorageClass default does not convert existing volumes. Confirm
  each backup has completed PodVolumeBackups with nonzero bytes before
  relying on it.

## Verification

`local-path.yml -e local_path_action=smoke` builds a throwaway
namespace with its own Delete-policy StorageClass (same provisioner),
writes a marker file from one pod, reads it back from a second pod
on the same PVC (the reader is applied only after the writer has
finished and exited), and tears everything down — including proof
that the Delete policy removed the PV and its directory. A green
smoke test is the definition of working: provisioning, persistence
across pods, and cleanup, with the one-time base path as the only
machine-config input.

## The one reboot

Adopting the provisioner cost exactly one rolling worker reboot:
adding the base path's `.keep` entry to the worker patch and
rebooting each worker once to materialize it (the standard
machine-config rule). That is the last storage-related reboot this
pattern should ever need — every volume from here on is created by
the provisioner, not by machine config.
