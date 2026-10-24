# Seerr on the Talos cluster (Argo CD)

Seerr runs from the bjw-s **app-template** chart (5.3.0, digest-pinned
images) as an Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application definition
is `../argocd/applications/seerr.yaml`. Syncs are manual, pruning is
off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/seerr/docker-compose.yml`
(image `ghcr.io/seerr-team/seerr:v3.5.1`, port 5055, `./config:/app/config`
relative to `/root` on the LXC).

Exposure is **tailnet-only** (Dave's standing decision): the pod mirrors
the Kiwix shape — a userspace Tailscale sidecar TCP-forwards 443 to an
in-pod Caddy on 8443, which terminates a real certificate (Cloudflare
DNS-01) for `seerr.tail.davegallant.ca` and proxies to Seerr on
127.0.0.1:5055. No Pangolin/Newt tunnel, no public ingress.

Secrets stay in Vault and outside Argo's ownership:

- `seerr-caddy-external` (key `cloudflare_api_token`) — materialized by
  `playbooks/talos-cluster/gitops-secrets.yml` from
  `cloudflare_dns_api_token`.
- `seerr-tailscale-auth` (key `TS_AUTHKEY`) — a one-use Headscale
  preauth key created by hand at first registration (below), deleted
  once the identity persists in the `seerr-tailscale-state` PVC.

Backups: the values carry a Velero Schedule (`seerr`, into the
velero namespace) in opt-in mode; the pod annotates
`backup.velero.io/backup-volumes: config-local`, so only the app config
volume is filesystem-backed-up. The tailscale identity volume is never
captured — restoring it would clone a live tailnet identity.

The local-path provisioner creates hostPath-backed PVs, which Velero does
not support for PodVolumeBackup. The `seerr-config-local` claim exposes its
directory through the static local PV in `config-local-pv.yaml`. Preserve
the PV's worker and path during recovery or relocation.
