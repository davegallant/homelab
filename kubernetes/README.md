# Kubernetes workloads

Talos runs application and platform workloads on three VMs across two Proxmox
hosts. Argo CD manages application resources from the tracked chart templates
and production values. Ansible manages infrastructure, external Secrets from
Vault, and selected ConfigMaps. Application syncs require manual approval.
All LXC-to-Kubernetes application migrations are complete. App READMEs cover
current configuration and service-specific operations; this directory holds
shared cluster operations and recovery guidance.

## Start here

| Task | Documentation |
|---|---|
| Inspect VM sizing, networking, and recovery constraints | [Cluster](cluster/README.md) |
| Update applications or recover Argo CD | [Release management](apps/argocd/MANAGEMENT.md), [Argo CD](apps/argocd/README.md) |
| Restore a namespace or rehearse Homepage recovery | [Backups and restore drill](BACKUPS.md) |
| Operate Alloy or diagnose Loki ingestion | [Observability](OBSERVABILITY.md) |
| Review Cilium policies and Pod Security exceptions | [Security](SECURITY.md), [Cilium](apps/cilium/README.md) |

## Repository layout

`kubernetes/` contains cluster configuration, application charts, production
values, policies, and runbooks. Provisioning and Vault integration remain in
`ansible/`; Talos lifecycle playbooks live in `ansible/playbooks/talos-cluster/`.

## Deployment ownership

Edit chart templates and `values.production.yaml`, review the change, then
sync the corresponding Application after the approved push reaches remote
`main`. Do not run Helm upgrade, rollback, or uninstall against resources
already owned by Argo CD. Legacy lifecycle playbooks guard against mutations
after handoff; their read-only verification actions remain useful.

Provision external resources with `gitops-secrets.yml` as described in
[release management](apps/argocd/MANAGEMENT.md). External Secret changes need
workload restarts; PostgreSQL credential rotation also needs a database role
password change. Homepage configuration and proxy code remain Ansible-managed.
Keep rendered Secrets and protected Talos credentials outside Git.

Talos playbooks in `ansible/playbooks/talos-cluster/` are manual and separate
from the LXC all-host deployment. Run commands from the directory specified
by each runbook, pass the Vault password file, and use the intended kubeconfig
and context. Read the cluster recovery constraints before restoring any VM.

## Applications

These directories contain configuration and current operating notes.
Application definitions are under [Argo CD](apps/argocd/).

| Application | Documentation |
|---|---|
| audiobookshelf | [Runbook](apps/audiobookshelf/README.md) |
| bentopdf | [Runbook](apps/bentopdf/README.md) |
| changedetection | [Runbook](apps/changedetection/README.md) |
| homepage | [Runbook](apps/homepage/README.md) |
| invidious | [Runbook](apps/invidious/README.md) |
| kiwix | [Runbook](apps/kiwix/README.md) |
| lidarr | [Runbook](apps/lidarr/README.md) |
| lubelogger | [Runbook](apps/lubelogger/README.md) |
| maloja | [Runbook](apps/maloja/README.md) |
| miniflux | [Runbook](apps/miniflux/README.md) |
| navidrome | [Runbook](apps/navidrome/README.md) |
| paperless-ngx | [Runbook](apps/paperless-ngx/README.md) |
| prowlarr | [Runbook](apps/prowlarr/README.md) |
| radarr | [Runbook](apps/radarr/README.md) |
| romm | [Runbook](apps/romm/README.md) |
| searxng | [Runbook](apps/searxng/README.md) |
| seerr | [Runbook](apps/seerr/README.md) |
| sonarr | [Runbook](apps/sonarr/README.md) |
| speedtest-tracker | [Runbook](apps/speedtest-tracker/README.md) |
| umami | [Runbook](apps/umami/README.md) |

## Platform

- [Argo CD](apps/argocd/README.md): application reconciliation and recovery.
- [Cilium](apps/cilium/README.md): CNI, network policies, and Hubble.
- [Monitoring](apps/monitoring/README.md): node and Kubernetes metrics.
- [NFS CSI](apps/nfs-csi/README.md): NAS-backed volumes.
- [Local-path provisioner](apps/local-path/README.md): dynamic node-local volumes.
- [Alloy](OBSERVABILITY.md): pod logs through the Kubernetes API.
- [Velero](BACKUPS.md): namespace and volume backups to Garage.

Node-local storage binds workloads to a worker. VM backups capture local
volume data; off-host etcd snapshots capture cluster state. Velero excludes
Secrets and live Tailscale identities. NAS data has separate protection;
check each workload's runbook for its actual backup scope.
