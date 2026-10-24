# Kiwix on Talos

Argo CD manages Kiwix from the local chart and
`values.production.yaml`; its Application is
`../argocd/applications/kiwix.yaml`. Follow the [release management
guide](../argocd/MANAGEMENT.md) for updates and recovery.

The ZIM library is served read-only from TrueNAS through the NFS CSI
driver. The NFS PV/PVC and the sidecar state volumes are defined in
`storage.yaml`. The Tailscale and Caddy state volumes are local to
`k8s-w-1`; preserve their identity and certificate state during recovery.

The `kiwix-daily` Velero schedule backs up Kubernetes resources only. The
library is protected by TrueNAS snapshots and Drive sync; the Tailscale
identity volume is excluded. See [backup and restore
procedures](../../BACKUPS.md) and [NFS CSI
notes](../nfs-csi/README.md).
