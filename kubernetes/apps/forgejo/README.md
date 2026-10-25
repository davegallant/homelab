# Forgejo production

Public Forgejo runs on Kubernetes following the successful 2026-10-25
cutover. Forgejo and Newt are each configured at one replica. The LXC
Forgejo server and Newt connector are stopped; their data is retained.
Resolve service failures in Kubernetes. Do not restart the LXC services or
reverse the cutover without Dave's explicit authorization.

## Runtime

- Official Forgejo chart 7.1.7, Forgejo 17.0.0 pinned by image digest.
- SQLite: `/data/gitea/gitea.db`; PostgreSQL HA and Redis Cluster disabled.
- Repository root: `/data/git/repositories`.
- `FORGEJO_WORK_DIR=/data/gitea` matches the copied configuration's
  `WORK_PATH` and is supplied to the application and chart init containers.
- `/data` uses the 5 GiB `forgejo-data-local` PVC on `k8s-w-1`.
  It was created with `volumeType: local`; the provisioned PV is type
  `local`, with a `Retain` reclaim policy. SQLite remains on local storage.
- [Public Forgejo](https://forgejo.davegallant.ca) uses the existing
  Pangolin Newt identity. The separate Newt Deployment connects to the
  same-namespace `forgejo:3000` Service. Cilium permits its TCP 3000 traffic.
- Git operations use HTTPS; Git-over-SSH is not exposed.
- `forgejo-external` and `forgejo-newt-external` are provisioned outside
  Argo CD from Vault. Keep secret values out of Git and command output.
- Host and Docker runners remain on the LXC; migrating the Forgejo server
  did not migrate its runners. Ansible workflows use the `tailscale` label
  and Docker workflows use `docker`.

## Cutover evidence

The final frozen copy contained 67,608 files, with an empty source versus
destination path-and-size manifest diff. Internal Service and Pod HTTP
checks and anonymous clones passed. A unique public request appeared in
the Kubernetes Forgejo logs, and Hubble confirmed allowed Newt traffic.
Public anonymous clone, disposable repository push, read-only host-runner
Ansible ping, and the Docker runner workflow all passed. Both disposable
repositories were deleted after verification.

## Storage and recovery

Read [the storage rules](../../STORAGE.md) and
[backup recovery guidance](../../BACKUPS.md) before changing volumes.
The annotation test produced a completed Velero data PodVolumeBackup with
989,859,411 bytes while Forgejo was running. Future backups must likewise
include a completed data PodVolumeBackup with nonzero bytes.

The retained `forgejo-data` PVC is the earlier hostPath-backed copy; it is
not the active claim. At cutover, Argo CD was Healthy and OutOfSync only
because this old claim was retained. Manual syncs must preserve it rather
than prune it. The helper Pods, source data, and migration archives are
retained pending separately approved cleanup. The stopped source is a
historical copy and must not overwrite newer Kubernetes writes.
