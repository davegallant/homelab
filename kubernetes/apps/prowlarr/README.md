# Prowlarr on the Talos cluster (Argo CD)

Prowlarr runs from the bjw-s **app-template** chart (5.3.0) as an
Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/prowlarr.yaml`. Syncs are
manual, pruning is off, and deleting the Application preserves the
workload.

Workload source of truth: `values.production.yaml`
(app `docker.io/linuxserver/prowlarr:2.6.5`, port 9696;
Flaresolverr `ghcr.io/flaresolverr/flaresolverr:v3.5.2`). All
state is the `/config` directory (SQLite database, config.xml);
there is no separate database; the app stores its state in the `/config` volume.

Exposure is **tailnet-only**: the pod mirrors the RomM shape —
userspace Tailscale sidecar → in-pod Caddy (8443, Cloudflare
DNS-01) → Prowlarr on 127.0.0.1:9696, at
`prowlarr.tail.davegallant.ca`, replacing the LXC's host-level
`tailnet_caddy` role.

Flaresolverr runs in-pod as a second app container, reachable at
127.0.0.1:8191. Prowlarr has no media mounts and never talks to
qBittorrent. The *arr applications use its in-cluster Service for
indexer lookups.

Secrets stay in Vault and outside Argo's ownership:
`prowlarr-caddy-external` from `playbooks/talos-cluster/gitops-secrets.yml`,
and the bootstrap-only one-use `prowlarr-tailscale-auth`. There is
deliberately no app Secret: Prowlarr's API key and its indexer/app
credentials live in its config, which arrives with the copied
`/config`.

Backups: Velero Schedule `prowlarr-daily` (in the values) with pod
annotation `backup.velero.io/backup-volumes: config-local`. The network
policy is the house default-deny CiliumNetworkPolicy, in the
values as `rawResources.defaultDenyNetworkPolicy`, extended with
two-way API access between Prowlarr and the three app namespaces.
