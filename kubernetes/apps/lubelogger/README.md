# LubeLogger on the Talos cluster (Argo CD)

LubeLogger runs from the bjw-s **app-template** chart (5.3.0) as an
Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application definition
is `../argocd/applications/lubelogger.yaml`. Syncs are manual, pruning
is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/lubelogger/docker-compose.yml`
(image `ghcr.io/hargata/lubelogger:v1.4.5`, port 8080). The compose
file's **eight named volumes** are consolidated into one local-path
PVC (`lubelogger-data`, 2Gi) mounted by subPath: `config`, `data`,
`translations`, `documents`, `images`, `temp`, `log`, and `keys`
(the ASP.NET DataProtection keys — losing them invalidates protected
data, so they are copied and backed up with everything else).

Exposure is **tailnet-only**: the pod mirrors the Kiwix shape —
userspace Tailscale sidecar → in-pod Caddy (8443, Cloudflare DNS-01)
→ LubeLogger on 127.0.0.1:8080, at `lubelogger.tail.davegallant.ca`.

Secrets stay in Vault and outside Argo's ownership:
`lubelogger-caddy-external` (from `gitops-secrets.yml`) and the
bootstrap-only one-use `lubelogger-tailscale-auth`.

Backups: Velero Schedule `lubelogger` (in the values, opt-in
mode) with pod annotation `backup.velero.io/backup-volumes: data-local`.
The local-path directory is exposed through a static local PV so Velero
can make a filesystem backup.
