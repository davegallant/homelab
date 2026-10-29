# NFS CSI driver (cluster storage platform)

## Current operations

Argo CD manages the production resources. Follow [release management](../argocd/MANAGEMENT.md)
for updates, external Secrets, and recovery. Use the tracked production values
and Application definition for desired state. Do not run Helm mutations against
resources owned by Argo CD.

## Mount and isolation constraints

Use each consumer's tracked PV for its server, export and mount options; verify
NAS export permissions against every address the selected node may use. Driver
installation does not prove a consumer can mount its export.

Scope controller policy narrowly in shared `kube-system`. Host-network node
plugins perform node-side mounts outside endpoint policy. Do not treat a pod
policy as a firewall for those mounts.

## Verification

`nfs-csi.yml -e nfs_csi_action=smoke` builds a throwaway namespace,
PV/PVC and pod against the Kiwix export, asserts a `*.zim` listing
comes back non-empty, and tears the whole rig down. A green smoke test
is the platform's definition of working: driver present, export
reachable from a real node, mount semantics sane.

## Backup posture

NFS-backed PV data is **never** Velero filesystem-backed-up: verify NAS snapshots, off-site copies and a restore separately. Velero schedules for consumers of this driver are
manifests-only, with the data volume named in the
backup-volumes-excludes annotation for explicitness.
