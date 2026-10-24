# Maloja on the Talos cluster (Argo CD)

Maloja runs from the bjw-s **app-template** chart (5.3.0) as an Argo
CD Application — no local chart. Desired state is
`values.production.yaml`; the Application definition is
`../argocd/applications/maloja.yaml`. Syncs are manual, pruning is
off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/maloja/docker-compose.yml`
(image `docker.io/krateng/maloja:3.2.9` digest-pinned, port 42010,
bind mount `$PWD/data:/data` — `/root/data` on the LXC). Environment
is carried over verbatim, including `MALOJA_FORCE_PASSWORD=stub`
(already committed in the LXC playbook; not a real credential —
access control is the tailnet itself).

Exposure is **tailnet-only**: userspace Tailscale sidecar → in-pod
Caddy (8443, Cloudflare DNS-01) → Maloja on 127.0.0.1:42010, at
`maloja.tail.davegallant.ca`.

Secrets stay in Vault and outside Argo's ownership:
`maloja-caddy-external` (from `gitops-secrets.yml`) and the
bootstrap-only one-use `maloja-tailscale-auth`.

Backups: Velero Schedule `maloja` (in the values, opt-in mode)
with pod annotation `backup.velero.io/backup-volumes: data-local`.
The local-path provisioner creates hostPath-backed PVs, which Velero does
not support for PodVolumeBackup. The `maloja-data-local` claim exposes its
directory through a static local PV. Preserve the PV's node and path during
recovery and consult the cluster recovery guide before relocating the workload.
