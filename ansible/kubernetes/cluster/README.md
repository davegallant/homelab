# Talos cluster pilot

This directory records the three-VM layout and the machine configuration
patches. Manual Ansible playbooks in `ansible/playbooks/talos-cluster/` provision
the VMs, generate protected Talos configs, bootstrap the cluster, and maintain
backups. The Talos credentials and kubeconfig live outside Git under
`~/.local/share/homelab-talos/` with private permissions.

| VM | Proxmox host | Role | vCPU | RAM | Disk | Storage |
|---|---|---|---:|---:|---:|---|
| `k8s-cp-1` | `pve-g3-1` | control plane | 2 | 4 GiB | 25 GiB | `moredata` |
| `k8s-w-1` | `pve-g3-1` | worker | 2 | 3 GiB | 25 GiB | `moredata` |
| `k8s-w-2` | `pve-g3-2` | worker | 2 | 2 GiB | 25 GiB | `local-lvm` |

`k8s-w-2` was initially provisioned at 1.5 GiB, then increased to 2 GiB after
the host retained more than 3 GiB available. The control plane keeps the
generated `node-role.kubernetes.io/control-plane:NoSchedule` taint; this is a
two-host pilot, not an HA control plane.

The node addresses are `.210`, `.211`, and `.212` on `192.168.1.0/24`, outside
OPNsense's active `.2-.99` DHCP pool. The gateway is `.1`, and Talos resolves
through AdGuard Home at `.77` with OPNsense at `.1` as fallback. The
`previous_address` values in `vars.yaml` document the one-time move from DHCP.
All three nodes were Ready at the static addresses after the transition.

The storage patches create the three local volume directories on every node.
Only `k8s-w-1` is eligible for the Homepage pod and its local PVs. If that
worker is lost, Homepage remains down until it returns or its data is restored
and deliberately relocated.

The existing 02:00 Proxmox snapshot job now includes all three Talos VMs and
stores them on `proxmox-backups` NFS. `backup-now.yml` takes a manual
backup; `snapshot-etcd.yml` also stores an etcd snapshot containing cluster state
in a protected directory on the same off-host store. VM backups include the
Homepage local PV paths. Before retiring the Homepage LXC, complete a recovery
drill and separately protect the operator's Talos credentials. The Alloy
DaemonSet follow-up is described in `../README.md`; it collects pod logs through
the Kubernetes API without node filesystem mounts.

Run these playbooks manually from `ansible/`, with the Ansible Vault password
file and `TALOSCTL` pointing at the matching v1.14.1 binary. Keep the
credential directory, off-host etcd snapshots, and Ansible Vault protected.
