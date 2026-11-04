# Arca

Arca is the tailnet-only website archive at `arca.tail.davegallant.ca`.
The Deployment runs the existing Python application with Chromium and Wget;
submitted URLs are untrusted, so Cilium permits only DNS and public HTTP/HTTPS
egress while blocking the LAN, link-local and tailnet ranges.

## Image and registry

The source repository is `dave/arca` in Forgejo. A trusted Forgejo Actions job
builds the image and publishes it to `forgejo.davegallant.ca/dave/arca`, tagged
with the source commit SHA. The production values must pin that tag and the
registry manifest digest. Do not sync while the values still say
`pending-publish` or have an empty digest.

The package is private. `ARCA_REGISTRY_WRITE_TOKEN` is a Forgejo Actions secret
with `write:package`; the workflow never prints it. Ansible Vault variable
`arca_registry_read_token` is a separate `read:package` token. Forgejo only
allows package scopes on account-wide tokens, so both tokens use the All
repositories option with only their respective package scope enabled.
The `gitops-secrets.yml` playbook provisions the pull token as the externally owned
`arca-registry-external` image pull Secret. Never put either token in Git or
shell output.

## Runtime and storage

- One replica, `Recreate` deployment strategy, pinned to `k8s-w-1`.
- Pod runs as UID/GID 1000 in a Restricted namespace, with all capabilities
  dropped, privilege escalation disabled, and a read-only root filesystem.
- `/data` contains both `index.sqlite3` and archived files. It uses a 5Gi
  `local-path` PVC annotated `volumeType: local`; do not use NFS for SQLite.
- `/tmp` is ephemeral and holds Chromium profile/cache files.
- The PodVolumeBackup annotation includes only the archive data volume.
- Velero backs up the `arca` namespace daily at 02:30 UTC with 336h retention;
  Kubernetes Secrets are excluded and recreated from Vault.

## Exposure and dependencies

The existing tailnet Gateway serves `arca.tail.davegallant.ca` on port 443 and
forwards to the `arca` Service on TCP 8099. Gatus checks `/healthz`; Homepage
already links to the same hostname. The app has no separate login, so keep this
route tailnet-only.

## Migration, validation and recovery

1. Publish the image and replace the pending tag/digest in
   `values.production.yaml`.
2. Apply `namespace.yaml`, provision the external image pull Secret from Vault,
   verify the Arca Application renders, and review its Argo diff before sync.
3. Verify the PVC's PV type is `local`, its worker is `k8s-w-1`, and disk/inode
   headroom is sufficient before copying any archive data.
4. Keep the existing LXC online while verifying pod readiness, Gateway route
   acceptance, ordinary DNS/TLS, and `/healthz`.
5. Stop the source application for a consistent copy. Record a frozen source
   path/size manifest, copy the files into `/data` as UID 1000, then require an
   empty manifest diff. Preserve the source data unchanged.
6. Verify the list and detail views, then require a completed Velero backup
   with a nonzero data PodVolumeBackup before declaring cutover complete.
7. For rollback, stop the Kubernetes Deployment, restore the old DNS/route
   ownership, and start the unchanged source LXC. Do not delete the PVC or
   source data as part of rollback.

Keep the LXC until the migration has passed the completed-backup gate and Dave
separately approves retirement.
