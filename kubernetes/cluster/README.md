# Talos cluster

This directory records the three-VM layout and the machine configuration
patches. Manual Ansible playbooks in `ansible/playbooks/talos-cluster/` provision
the VMs, generate protected Talos configs, bootstrap the cluster, and maintain
backups. The Talos credentials and kubeconfig live outside Git under
`~/.local/share/homelab-talos/` with private permissions.

| VM | Proxmox host | Role | vCPU | RAM | Disk | Storage |
|---|---|---|---:|---:|---:|---|
| `k8s-cp-1` | `pve-g3-1` | control plane | 2 | 6 GiB | 25 GiB | `moredata` |
| `k8s-w-1` | `pve-g3-1` | worker | 3 | 10 GiB | 80 GiB | `moredata` |
| `k8s-w-2` | `pve-g3-2` | worker | 2 | 8 GiB | 25 GiB | `local-lvm` |

Sizing in the table is the live Proxmox VM size, verified 2026-10-28 via node capacity (w-1 10 GiB, w-2 8 GiB). It does NOT currently match [vars.yaml](vars.yaml), which still lists w-1 8192 MiB and w-2 4608 MiB — those VMs were resized in Proxmox outside the repo, so vars.yaml memory is stale until it is updated to match live. Resize workers through
`resize-worker.yml` after checking Proxmox host availability and retaining the
2 GiB host memory reserve. Compare worker allocatable memory and scheduled
requests before adding workloads; host free memory alone does not establish
whether a Pod fits. The control plane keeps its
`node-role.kubernetes.io/control-plane:NoSchedule` taint. This cluster has one
control-plane VM across two Proxmox hosts and does not provide control-plane HA.

On 2026-10-25, `k8s-w-1`'s Proxmox disk was grown from 25 GiB to 80 GiB after
repeated `DiskPressure` caused workload disruption. The node remained Ready with `DiskPressure=False` after the resize. The resize does not relocate node-local
PVCs; workloads using them remain tied to `k8s-w-1`.

A protected, checksum-verified off-host etcd snapshot (`etcd-homelab-20261023T181653Z.snap`) was taken before the 2026-10-23 resize; that short post-resize observation does not replace validation during the next OCR, scan, and backup peaks.

The node addresses are `.210`, `.211`, and `.212` on `192.168.1.0/24`, outside
OPNsense's active `.2-.99` DHCP pool. The gateway is `.1`, and Talos resolves
through AdGuard Home at `.77` with OPNsense at `.1` as fallback. The
`previous_address` values in `vars.yaml` document the one-time move from DHCP.
All three nodes were Ready at the static addresses after the transition. `k8s-w-1` also carries `192.168.1.152` (`extra_addresses` in `vars.yaml`, added for qBittorrent egress); on 2026-10-28 it was the node's reported InternalIP, and NFS exports listing only `.211` denied w-1 mounts until `.152` was added — any host-specific allowlist must include both.

`k8s-w-2` has the Intel HD Graphics 630 at PCI `0000:00:02.0` passed through
from `pve-g3-2` (Proxmox VMID 147). The Talos installer uses the i915
system extension schematic
`dc8730aa8cc7bfa5ef7e2b3284248f2631135b2faf4ae11aa997a0c1987b0eee`; the
Intel device plugin advertises `gpu.intel.com/i915` to pods. After a worker
rebuild or upgrade, verify the `i915` driver, `/dev/dri/renderD128`, and the
advertised resource before scheduling GPU workloads. On 2026-10-27, the Intel
HD Graphics 630 on `pve-g3-1` was passed through to `k8s-w-1` (VMID 146)
using the same Talos i915 extension. The Intel GPU plugin runs on both workers (verified 2026-10-28). Jellyfin now runs on
Kubernetes and requests the Intel GPU for hardware transcoding.

The cluster's steady-state CNI is Cilium `1.20.3` on Kubernetes `1.37.2` (upgraded 2026-10-28; previously `1.37.0`/`1.37.1`),
using cluster-pool pod CIDR `10.245.0.0/16` and VXLAN UDP `8473`. Talos has
`cluster.network.cni.name: none`; Flannel has been removed, and kube-proxy is
replaced by Cilium. See [`../apps/cilium/`](../apps/cilium/)
for the live-migration record, policy inventory, and recovery path.

The storage patches create the local volume roots on every node (Homepage, Kiwix, Miniflux, and the local-path provisioner root; see `worker.patch.yaml.j2`).
Only `k8s-w-1` is eligible for the Homepage pod and its local PVs. If that
worker is lost, Homepage remains down until it returns or its data is restored
and deliberately relocated.

The existing 02:00 Proxmox snapshot job now includes all three Talos VMs and
stores them on `proxmox-backups` NFS. `backup-now.yml` takes a manual
backup; `snapshot-etcd.yml` also stores an etcd snapshot containing cluster state
in a protected directory on the same off-host store. VM backups include the
Homepage local PV paths. The 02:00 `proxmox-backups` vzdump job stages
temporary files under local `/var/tmp` on the executing Proxmox node; backup
archives still go to NFS. Keep `/var/tmp` available on both Proxmox nodes
because unprivileged LXC backup workers cannot write to the restricted NFS
export. Homepage's former LXC
playbook has been retired; keep the recovery drill current and separately
protect the operator's Talos credentials. The Alloy
DaemonSet is described in [the logging runbook](../OBSERVABILITY.md); it collects pod logs through
the Kubernetes API without node filesystem mounts.

Run these playbooks manually from `ansible/`, with the Ansible Vault password
file and `TALOSCTL` pointing at a talosctl binary of the same minor version as the cluster (patch-level differences are allowed by the generate-config gate; e.g. talosctl 1.14.3 for a 1.14.1 cluster). Keep the
credential directory, off-host etcd snapshots, and Ansible Vault protected.

## Updating Talos

There are four different updates; do not conflate them. Talos version is
currently MIXED, verified 2026-10-28: `k8s-w-2` is on v1.14.3 (upgraded
2026-10-28), `k8s-cp-1` and `k8s-w-1` are still on v1.14.1. Do not bump
`vars.yaml` to v1.14.3 until all three nodes are upgraded and verified
(step 7). On any failure gate: halt, preserve state and logs, and do
not proceed to the next node.

### Machine-config change only (no OS version change)

1. Edit `vars.yaml` or the `*.patch.yaml.j2` files in this directory.
2. Regenerate with `just run talos-cluster/generate-config` (run from the
   repo root; `TALOSCTL` must be the same minor as the cluster).
3. Reapply with `just run talos-cluster/reapply-config` — this is the
authenticated path for live nodes. `apply-config.yml` is the insecure
   initial-provision path only.
4. Verify the node is Ready and its workloads return before touching
   another node.

### VM sizing change

Resize workers through `resize-worker.yml` (see the sizing paragraph above).
Check Proxmox host availability first and retain the 2 GiB host memory
reserve. A disk resize does not relocate node-local PVCs.

### Talos OS upgrade (one node at a time, workers first)

Order: workers first, the single control plane last, so the new image is
proven before touching the only etcd host. Expect API downtime during the
control-plane reboot — there is no control-plane HA.

1. Backups first: a Proxmox snapshot (`backup-now.yml`, or the 02:00 job)
   and an off-host etcd snapshot (`snapshot-etcd.yml`). Confirm Argo
   Applications are Synced/Healthy and all nodes are Ready.
2. Read the target Talos release notes for machine-config breaking
   changes and Cilium/Kubernetes compatibility. Latest Talos
   releases: https://github.com/siderolabs/talos/releases — build
   the installer image at https://factory.talos.dev/ . Step through
   minors:
   upgrade to the latest patch of each intermediate minor, never skip
   a minor (e.g. 1.14.x → latest 1.14 patch → 1.15.x, not 1.14 → 1.16).
3. Build the installer image in the Talos Image Factory with the same
   system extensions this cluster uses — currently the i915 extension
   for GPU passthrough. If the extension set is unchanged, the schematic ID stays the
   same and only the version tag changes; if extensions change,
   generate a new schematic. Do not use the stock installer image
   without the extension, or GPU workloads break. The Image Factory's "Upgrading Talos" section gives
   the exact image path for the schematic.
4. Issue the upgrade one node at a time, with `--endpoints` set to
   the control plane (as with `upgrade-k8s`, `--nodes` alone is not
   enough). Set the image once, then run one short command per
   node, in this order, verifying each node is Ready on the new
   version before the next. This cluster's i915 schematic is
   `dc8730aa8cc7bfa5ef7e2b3284248f2631135b2faf4ae11aa997a0c1987b0eee`;
   the schematic ID is based on its contents, so the same ID is
   reused with the new version tag — confirm the exact string in
   the Image Factory before running it. Spelled out for the
   1.14.1 to 1.14.3 upgrade (w-2 completed 2026-10-28):

   ```sh
   IMAGE=factory.talos.dev/metal-installer/dc8730aa8cc7bfa5ef7e2b3284248f2631135b2faf4ae11aa997a0c1987b0eee:v1.14.3
   # w-2 (192.168.1.212) — done 2026-10-28, skip if already on 1.14.3
   talosctl --endpoints 192.168.1.210 --nodes 192.168.1.212 upgrade --image "$IMAGE" --wait
   # w-1 (192.168.1.152)
   talosctl --endpoints 192.168.1.210 --nodes 192.168.1.152 upgrade --image "$IMAGE" --wait
   # control plane (192.168.1.210) — last
   talosctl --endpoints 192.168.1.210 --nodes 192.168.1.210 upgrade --image "$IMAGE" --wait
   ```

   Talos cordons and drains the node itself, installs to the A-B
   partition, and reboots. A failed boot rolls back to the previous
   image automatically; if workloads fail after a successful boot, use
   `talosctl rollback` and halt.
5. Local-PV note: from Talos 1.8 onwards, `--preserve` is automatic
   and the system disk is never wiped during an upgrade, so local PVs
   (Homepage on w-1, and others under `/var/mnt/local-path`) are not
   erased by a default upgrade the way they were pre-1.8. Still
   verify local PVs return after the first node before proceeding
   to the next — they are not replicated, so a Velero restore is
   the fallback if one does not.
6. Verify before the next node: node Ready, Talos version, Cilium
   agents healthy, GPU plugin Running and `gpu.intel.com/i915`
   advertised on GPU workers, Gateway reachable, and NFS mounts
   working (host-specific allowlists must include every node address,
   including w-1's `.152` — see the addresses paragraph above).
7. Only after all nodes are upgraded and verified, bump `vars.yaml`
   (`talos_version`, `talos_iso_filename`, `talos_iso_sha256`) so a
   future rebuild does not reinstall the old version, regenerate
   configs with the new-minor talosctl, reapply, and update the
   version lines in this README. Commit and push the vars/README
   change as its own change.

### Kubernetes upgrade (separate from Talos)

A Talos OS upgrade does not upgrade Kubernetes by default. Do it in a
separate window; it does not depend on the Talos upgrade — the 1.37.2
upgrade was run 2026-10-28 before the Talos 1.14.3 upgrade started.
Check the latest patch first at https://kubernetes.io/releases:

```sh
talosctl --endpoints 192.168.1.210 --nodes 192.168.1.210 upgrade-k8s --to 1.37.2 --dry-run
```

`--endpoints` must be a control-plane address; `--nodes` alone is not
enough. Without `--endpoints`, the 2026-10-28 dry run failed with
`PermissionDenied: no request forwarding` at the "getting server
version" step, and adding `--endpoints 192.168.1.210` fixed it (the
default talosconfig on the operator machine works; no `--talosconfig`
flag was needed).

Remove `--dry-run` only after the dry run is clean. The command is sent
to the control plane but upgrades all members.

## Related runbooks

- [Application and platform overview](../README.md)
- [Backups and Homepage restore drill](../BACKUPS.md)
- [Network policies and Pod Security](../SECURITY.md)
