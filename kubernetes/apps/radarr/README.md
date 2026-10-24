# Radarr on the Talos cluster (Argo CD)

Radarr runs from the bjw-s **app-template** chart (5.3.0) as an Argo CD
Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/radarr.yaml`. Syncs are manual,
pruning is off, and deleting the Application preserves the workload.

Workload source of truth: `values.production.yaml`
(app `docker.io/linuxserver/radarr:6.4.4`, port 7878). All state is
the `/config` directory (SQLite database, config.xml, logs); there
is no separate database.

Exposure is **tailnet-only**: the pod mirrors the RomM shape —
userspace Tailscale sidecar → in-pod Caddy (8443, Cloudflare DNS-01)
→ Radarr on 127.0.0.1:7878, at `radarr.tail.davegallant.ca`,
replacing the LXC's host-level `tailnet_caddy` role.

**qBittorrent remains on its LXC**, with its static LAN IP and
OPNsense → Mullvad policy route. This pod reaches the qBittorrent API
over the LAN. The shared media tree is a
static NFS PV (`storage.yaml`) mounted at `/mnt` — the identical
path the LXC uses — so every path in Radarr's database stays true
and hardlink imports keep working: NFS link/rename are server-side
operations within the export, unaffected by which client asks. The
tree never moves and is never Velero-backed-up (TrueNAS snapshots +
Drive sync).

Secrets stay in Vault and outside Argo's ownership:
`radarr-caddy-external` from `playbooks/talos-cluster/gitops-secrets.yml`,
and the bootstrap-only one-use `radarr-tailscale-auth`. There is
deliberately no app Secret: Radarr's API key and its qBittorrent
credentials live in `config.xml` in `/config`.

Backups: Velero Schedule `radarr-daily` (in the values) with pod
annotation `backup.velero.io/backup-volumes: config-local`. The network
policy is the house default-deny CiliumNetworkPolicy, in the values
as `rawResources.defaultDenyNetworkPolicy`, plus the qBittorrent
exception described there.
