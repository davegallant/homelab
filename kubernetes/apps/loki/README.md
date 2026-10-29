# Loki

The chart defines Loki as a single instance on `k8s-w-1`, with its
filesystem store and compactor state on an annotated local-path volume. A
userspace Tailscale sidecar registers the `loki` tailnet identity with
`tag:loki`; its state volume is excluded from Velero to avoid identity cloning.
`provision.yml` creates a one-use registration Secret when necessary. Protect
the identity volume and recreate the Secret only when registering a new node.

Kubernetes Alloy writes to the ClusterIP service. LXC Alloy shippers use the
`loki` tailnet name on port 3100; the endpoint has no application-level
authentication, so Headscale ACLs and Cilium policy restrict access.
See the [VictoriaMetrics chart](../victoriametrics/chart/) for its configuration.

The daily Velero schedule backs up the data PVC and excludes Secrets. A
filesystem backup of a live Loki store is not an application-consistent
snapshot; recovery must be tested and can lose recent logs. The stopped LXC
source is retained for rollback during cutover. Verify the backup phase and a
nonzero PodVolumeBackup, and verify the first scheduled run separately.
