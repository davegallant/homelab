# ChangeDetection on the Talos cluster (Argo CD)

ChangeDetection runs from the bjw-s **app-template** chart (5.3.0) as
an Argo CD Application — no local chart. Desired state is
`values.production.yaml`; the Application definition is
`../argocd/applications/changedetection.yaml`. Syncs are manual,
pruning is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/changedetection/docker-compose.yml`
(image `docker.io/dgtlmoon/changedetection.io:0.60.9` digest-pinned,
port 5000, `./changedetection:/datastore` — `/root/changedetection`
on the LXC). The LXC runs without the optional browser sidecar;
parity is kept — no browser container here either. (`HIDE_REFERER=true`
carried over.)

Exposure is **tailnet-only**: userspace Tailscale sidecar → in-pod
Caddy (8443, Cloudflare DNS-01) → ChangeDetection on 127.0.0.1:5000,
at `changedetection.tail.davegallant.ca`.

The Cilium default-deny policy is in `values.production.yaml` under
`rawResources.defaultDenyNetworkPolicy`. It allows same-namespace traffic,
cluster DNS and cluster entities, allows ChangeDetection's internet fetches,
and explicitly denies the LAN, service, and pod CIDR ranges.

Secrets stay in Vault and outside Argo's ownership:
`changedetection-caddy-external` (from `gitops-secrets.yml`) and the
bootstrap-only one-use `changedetection-tailscale-auth`.

Backups: Velero Schedule `changedetection` (in the values,
opt-in mode) with pod annotation
`backup.velero.io/backup-volumes: datastore`.
