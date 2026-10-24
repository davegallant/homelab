# Homepage on Talos

Homepage runs with userspace Tailscale and Caddy sidecars in one Pod. Argo CD
manages the workload from [the local chart](chart/) and
[production values](values.production.yaml). Follow
[release management](../argocd/MANAGEMENT.md) for updates and recovery.

## Configuration

- Edit services, settings, and icons in [config/](config/).
- Edit outbound HTTP and WebSocket proxy handling in [proxy-agent.cjs](proxy-agent.cjs).
- Apply these external ConfigMaps and Vault-backed Secrets through
  `playbooks/talos-cluster/gitops-secrets.yml`, then restart the Deployment
  to refresh subPath mounts. If changing the tracked configuration checksum,
  update `configChecksum` in production values and approve an Argo CD sync.
- Keep rendered Vault values outside Git. The Ansible values bridge remains
  available for bootstrap; production references external Secrets and ConfigMaps.

## Networking

Tailscale Serve forwards tailnet TCP 443 to Caddy on loopback port 8443.
Caddy uses Cloudflare DNS-01 certificates. The userspace sidecar also exposes
an HTTP proxy for outbound tailnet requests. Homepage's Node preloader routes
private widget requests through it, including the TrueNAS WebSocket upgrade.
Homepage creates custom HTTP agents, so proxy environment variables alone
are insufficient. Configured non-tailnet widget hosts connect directly.

Keep the Pod Security baseline: a kernel-mode sidecar requiring `NET_ADMIN`,
`NET_RAW`, or `/dev/net/tun` needs a separately reviewed exception.

## Storage and backups

[storage.yaml](storage.yaml) defines three static local PVs/PVCs for config,
Caddy certificates, and Tailscale identity. Storage remains outside the chart.
The PVs and Pod are pinned to `k8s-w-1`; losing that worker takes Homepage
down until recovery or deliberate relocation. Preserve the PVC-backed identity
across upgrades and never clone it into a running restore drill.

`/app/config` is writable because Homepage generates files and logs there.
Managed settings and services files overlay it from a ConfigMap; icons use
a separate binary ConfigMap. Imported runtime files on the PVC remain outside
the tracked config until explicitly migrated into Ansible-managed templates.

The chart defines `homepage-daily`. Velero backs up config and Caddy state,
excludes Secrets, and excludes the live Tailscale identity and ephemeral
Caddy runtime. A successful application backup needs a Completed Backup and
two Completed PodVolumeBackups. VM backups also cover local storage.
See [backup and restore procedures](../../BACKUPS.md) and
[cluster recovery constraints](../../cluster/README.md).

## Verification

From `ansible/`, with the protected kubeconfig available:

```sh
export KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig"
ansible-playbook playbooks/talos-cluster/homepage.yml \
  -i inventory --vault-password-file .vault_pass
ansible-playbook playbooks/talos-cluster/verify-cutover.yml \
  -i inventory --vault-password-file .vault_pass
```

The Homepage playbook defaults to read-only verification. Its historical
adoption action refuses mutations when Argo CD owns production. Rehearsal
targets a separate drill namespace; review the restore runbook before using it.
Use Argo CD for normal updates and rollback. The former Homepage LXC is retired.

Verify widget API calls as well as the dashboard root. Avoid running Node HTTP
probes inside the Homepage container: its preloader changes outbound requests.
The active hostname must resolve to the Kubernetes tailnet identity and return
HTTP 200 with valid TLS.
