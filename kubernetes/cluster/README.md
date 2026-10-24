# Talos cluster

This directory records the three-VM layout and the machine configuration
patches. Manual Ansible playbooks in `ansible/playbooks/talos-cluster/` provision
the VMs, generate protected Talos configs, bootstrap the cluster, and maintain
backups. The Talos credentials and kubeconfig live outside Git under
`~/.local/share/homelab-talos/` with private permissions.

| VM | Proxmox host | Role | vCPU | RAM | Disk | Storage |
|---|---|---|---:|---:|---:|---|
| `k8s-cp-1` | `pve-g3-1` | control plane | 2 | 6 GiB | 25 GiB | `moredata` |
| `k8s-w-1` | `pve-g3-1` | worker | 2 | 8 GiB | 25 GiB | `moredata` |
| `k8s-w-2` | `pve-g3-2` | worker | 2 | 4.5 GiB | 25 GiB | `local-lvm` |

Sizing in the table follows [vars.yaml](vars.yaml). Resize workers through
`resize-worker.yml` after checking Proxmox host availability and retaining the
2 GiB host memory reserve. Compare worker allocatable memory and scheduled
requests before adding workloads; host free memory alone does not establish
whether a Pod fits. The control plane keeps its
`node-role.kubernetes.io/control-plane:NoSchedule` taint. This cluster has one
control-plane VM across two Proxmox hosts and does not provide control-plane HA.

The post-resize observation on 2026-10-23 ran from 18:19 to 18:24 UTC.
All deployments recovered, all 35 Cilium endpoints were ready, and no
container restart counts increased after workload recovery. w-2's full
memory PSI `avg60` fell from 4.84% before the resize to 0.00%; its final
available memory was about 1.75 GiB. `pve-g3-2` retained about 2.48 GiB
available. This short observation does not replace validation during the
next OCR, scan, and backup peaks. A protected, checksum-verified off-host
etcd snapshot was taken before the resize:
`etcd-homelab-20261023T181653Z.snap`.

The node addresses are `.210`, `.211`, and `.212` on `192.168.1.0/24`, outside
OPNsense's active `.2-.99` DHCP pool. The gateway is `.1`, and Talos resolves
through AdGuard Home at `.77` with OPNsense at `.1` as fallback. The
`previous_address` values in `vars.yaml` document the one-time move from DHCP.
All three nodes were Ready at the static addresses after the transition.

The cluster's steady-state CNI is Cilium `1.20.3` on Kubernetes `1.37.0`,
using cluster-pool pod CIDR `10.245.0.0/16` and VXLAN UDP `8473`. Talos has
`cluster.network.cni.name: none`; Flannel has been removed, while kube-proxy
remains enabled. See [`../apps/cilium/`](../apps/cilium/)
for the live-migration record, policy inventory, and recovery path.

The storage patches create the three local volume directories on every node.
Only `k8s-w-1` is eligible for the Homepage pod and its local PVs. If that
worker is lost, Homepage remains down until it returns or its data is restored
and deliberately relocated.

The existing 02:00 Proxmox snapshot job now includes all three Talos VMs and
stores them on `proxmox-backups` NFS. `backup-now.yml` takes a manual
backup; `snapshot-etcd.yml` also stores an etcd snapshot containing cluster state
in a protected directory on the same off-host store. VM backups include the
Homepage local PV paths. Homepage's former LXC playbook has been retired; keep
the recovery drill current and separately protect the operator's Talos
credentials. The Alloy
DaemonSet is described in [the logging runbook](../OBSERVABILITY.md); it collects pod logs through
the Kubernetes API without node filesystem mounts.

Run these playbooks manually from `ansible/`, with the Ansible Vault password
file and `TALOSCTL` pointing at the matching v1.14.1 binary. Keep the
credential directory, off-host etcd snapshots, and Ansible Vault protected.

## Related runbooks

- [Application and platform overview](../README.md)
- [Backups and Homepage restore drill](../BACKUPS.md)
- [Network policies and Pod Security](../SECURITY.md)
