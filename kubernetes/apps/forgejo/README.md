# Forgejo production migration

The LXC Forgejo remains the live server until the data copy, restore drill,
and HTTPS cutover checks pass. Do not sync this Application above zero
replicas before the staging copy and backup gates are complete.

## Runtime

- Upstream `forgejo-helm/forgejo` chart 7.1.7, Forgejo 17.0.0 pinned to the
  live image digest.
- SQLite at `/data/gitea/gitea.db`; PostgreSQL HA and Redis Cluster are off.
- `/data` is a 5 GiB `local-path` PVC pinned to `k8s-w-1`. The live tree is
  about 1.11 GB; 5 GiB leaves growth and SQLite maintenance headroom without
  placing SQLite on NFS. The local-path storage class retains the volume.
- Public HTTPS remains at `https://forgejo.davegallant.ca` via the existing
  Pangolin Newt identity. A same-namespace Service named `forgejo` preserves
  the current Pangolin target `forgejo:3000`. The chart does not support
  injecting an extra container, so Newt is deployed as a separate, staged
  Deployment targeting that Service. It stays at zero replicas until the
  LXC Newt connector is stopped for the identity handoff.
- Git-over-SSH never worked on the live LXC. This migration preserves the
  working HTTPS service and does not expose SSH.
- `forgejo-external` is managed outside Argo CD from Vault and contains
  `ROOT_URL`, `PANGOLIN_ENDPOINT`, `NEWT_ID`, and `NEWT_SECRET`. Do not put
  these values in Git or print them. Reuse the existing Newt identity; do
  not rotate it.

## Staging and cutover gates

1. Apply `namespace.yaml`, provision `forgejo-external` through the protected
   Vault flow, apply the `homelab-platform` AppProject and Application, and
   manually sync without prune or force. Confirm full Application manifest
   generation and Healthy status at zero replicas.
2. Bind `forgejo-data` on `k8s-w-1` with a temporary helper Pod. Freeze writes
   at the source, create a per-file path-and-size manifest, copy all of
   `/data`, and compare manifests until the diff is empty. Restart the LXC
   Forgejo immediately after the frozen copy; do not modify or delete its
   data.
3. Run a Velero backup that includes the Forgejo PVC and verify a completed
   PodVolumeBackup. Restore into an isolated scratch namespace/PVC and verify
   the restored file manifest. Never restore over the production PVC.
4. For cutover, stop only the LXC Newt connector, set both Forgejo and the
   Kubernetes Newt Deployment to one replica, and manually sync. Verify the
   public HTTPS UI and HTTPS clone/push, then the host and Docker runner
   workflows. Leave the LXC Forgejo server and its `/data` intact as rollback.
5. Rollback by scaling Kubernetes Forgejo/Newt to zero, restarting the LXC
   Newt connector, and confirming the public URL serves the LXC again. Do not
   delete LXC data, old configs, volumes, or POC files.

## Storage and recovery

The PVC is local to `k8s-w-1`, with a `Retain` reclaim policy; it is not NAS
storage and must be restored to a scratch PVC on the intended worker. Velero
must capture the data volume with a PodVolumeBackup. Keep the LXC as the
authoritative rollback copy until the soak period is explicitly complete.
