# Kubernetes workloads

Talos runs application and platform workloads on three VMs across two Proxmox
hosts. Argo CD manages application resources from the tracked chart templates
and production values. Ansible manages infrastructure, external Secrets from
Vault, and selected ConfigMaps. Application syncs require manual approval.
Immich now runs on Kubernetes with its original LXC stopped and its original
DNS name routed to the cluster. Application configuration lives beside each
Argo CD definition; this directory holds shared cluster operations and
recovery guidance.

## Start here

| Task | Documentation |
|---|---|
| Inspect VM sizing, networking, and recovery constraints | [Cluster](cluster/README.md) |
| Update applications or recover Argo CD | [Release management](apps/argocd/MANAGEMENT.md), [Argo CD](apps/argocd/README.md) |
| Restore a namespace or rehearse Homepage recovery | [Backups and restore drill](BACKUPS.md) |
| Add any volume to any app | [Storage - canonical rule, read first](STORAGE.md) |
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

Application definitions are under [Argo CD](apps/argocd/applications/).
Each application directory contains its chart, production values, storage,
and policy resources.

## Platform

- [Argo CD](apps/argocd/README.md): application reconciliation and recovery.
- [Cilium](apps/cilium/README.md): CNI, network policies, and Hubble.
- [Monitoring](apps/monitoring/README.md): node and Kubernetes metrics.
- [NFS CSI](apps/nfs-csi/README.md): NAS-backed volumes.
- [Local-path provisioner](apps/local-path/README.md): dynamic node-local volumes.
- [Storage](STORAGE.md): canonical local-storage rule and new-app checklist - read before adding any volume.
- [Alloy](OBSERVABILITY.md): pod logs through the Kubernetes API.
- [Grafana](apps/grafana/README.md): dashboards and alerts.
- [Loki](apps/loki/README.md): log storage and ingestion.
- [Velero](BACKUPS.md): namespace and volume backups to Garage.

Node-local storage binds workloads to a worker. VM backups capture local
volume data; off-host etcd snapshots capture cluster state. Velero excludes
Secrets and live Tailscale identities. NAS data has separate protection;
check each workload's runbook for its actual backup scope.
