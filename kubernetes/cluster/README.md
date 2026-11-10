# Talos cluster

This directory records the three-VM layout and the machine configuration
patches. Manual Ansible playbooks in `ansible/playbooks/talos-cluster/` provision
the VMs, generate protected Talos configs, bootstrap the cluster, and maintain
backups. The Talos credentials and kubeconfig live outside Git under
`~/.local/share/homelab-talos/` with private permissions.

## Configuration and recovery constraints

[vars.yaml](vars.yaml) and machine patches define rebuild configuration;
they do not establish live VM sizing, node addresses or installed versions.
Compare Proxmox, Talos and Kubernetes before resizing, upgrading or rebuilding.

This design has a single control plane. Its restart interrupts the API.
Local PVs bind workloads to their worker; resizing a disk does not relocate
them. Isolate VM restores until node identity and etcd membership are reconciled.
Protect Talos credentials, Vault and off-host etcd snapshots separately.

Use the guarded resize playbooks after verifying a fresh off-host backup and
host storage/memory headroom. A Proxmox disk expansion may require a reboot
before Talos grows its filesystem. Never infer completion from Proxmox size
alone. Obtain Dave's explicit approval before any node reboot. First verify
all expected nodes Ready and Applications Synced/Healthy, subject to the
watchdog exception below, then take an off-host etcd snapshot. Afterward verify
capacity, DiskPressure, local mounts and workload health. On a failed gate,
halt and preserve state; do not shrink disks
or reboot another node as a workaround.

The `backup-watchdog` Application may remain Degraded because an earlier
CronJob failed. For manual health gates, accept this only when the Application
is Synced, the failed Job and its cause are identified, the cause is resolved,
and a fresh watchdog check against live data reports no gaps. Verify current
backup and volume-backup results independently; a successful manual check does
not prove the next scheduled run will succeed. Any other degraded Application
still fails the gate. The control-plane resize playbook defaults to the strict
gate. To use the exception, provide `talos_control_plane_watchdog_exception=true`,
`talos_control_plane_watchdog_review_reason` describing the identified and
resolved failure, and `talos_control_plane_watchdog_evidence_job` naming a
successful watchdog Job in `velero`. Its gap-free report and completion must
be less than an hour old and later than the latest scheduled watchdog run.
The playbook validates the evidence before and after the resize; all other
Applications must remain Synced and Healthy.

### Investigating node disk usage

Use the current node address from Kubernetes and supply it as both the Talos
node and endpoint when the local Talos configuration has no default endpoint:

```sh
kubectl get node k8s-w-1 -o wide
talosctl -n <node-ip> -e <node-ip> list /var/mnt/local-path
talosctl -n <node-ip> -e <node-ip> usage -H -d 1 /var/mnt/local-path
```

The directory names include the namespace and PVC name. `usage` walks the
files and can take several minutes; interrupting it prints the entries scanned
so far. To narrow a slow scan, pass an individual directory from `list` to
`usage`. Alternatively, run `kubectl exec` with `du -sh` on a mounted local
configuration directory, for example `/config` in Jellyfin. Measure its
transcode cache separately with `du -sh /cache/transcodes`.

Avoid a recursive scan of all `/var`: kubelet directories contain mounted NFS
shares, so it can traverse remote media, take a long time, and report remote
usage or permission errors. Kubelet volume statistics for local-path PVCs can
report the usage of the entire shared filesystem for each PVC; do not sum or
interpret those values as individual PVC sizes. Check filesystem capacity and
DiskPressure separately from directory sizes.

Check every node address against NFS exports and firewall allowlists; an extra
address can become Kubernetes InternalIP. Verify GPU driver, render device and
advertised resources after worker rebuilds or upgrades. Preserve the configured
installer extensions.

## Updating Talos

Check installed Talos versions on every node before selecting an upgrade
path. Configuration pins are rebuild inputs, not an upgrade completion record.
On a failed gate, halt and preserve state and logs.

### Machine-config change only (no OS version change)

1. Edit `vars.yaml` or the `*.patch.yaml.j2` files in this directory.
2. Regenerate with `just run talos-cluster/generate-config` (run from the
   repo root; `TALOSCTL` must be the same minor as the cluster).
3. Reapply with `just run talos-cluster/reapply-config` — this is the
authenticated path for live nodes. `apply-config.yml` is the insecure
   initial-provision path only.
4. Verify the node is Ready and its workloads return before touching
   another node.

### Talos apply is a full replacement, not a patch

A machine-config apply replaces the node's entire configuration. Any
feature or document omitted from the applied config is disabled on that
node, even if the intent was only to change one address or setting.
Never apply a protected, redacted, or otherwise partial config as a live
config: always start from the complete generated config and diff its
features and documents against the live config before applying.

Incident 2026-11-04: applying a config whose machine.features contained
only diskQuotaSupport: true disabled KubePrism on w-1, because KubePrism
was omitted. With no listener on 127.0.0.1:7445, the w-1 Cilium agent
could not reach the local Kubernetes API, stayed in Init, and w-1's pod
network went down — even though the interface change that prompted the
apply had succeeded. The fix was re-applying the complete generated
config with KubePrism preserved, not another Cilium change.

On Talos 1.14, KubePrism is a KubePrismConfig document, not the legacy
machine.features.kubePrism field. Adding the legacy field alongside
that document is rejected by Talos; preserve the document instead.

Related: config address order alone does not prove the live interface
primary. After any address change on a worker, verify the live connected
route's preferred source (for w-1, routes to the other nodes must source
from .211, with .152 secondary for worker egress), not just the order
listed in the generated config.

### VM sizing change

`vars.yaml` is the source of truth for Talos VM sizing. Update the affected
node's target there before changing its Proxmox VM: `memory_mib` for RAM,
`vcpu` for CPU, and `disk_gib` for the system disk. These are Proxmox settings,
not fields in the generated Talos machine configuration. The memory and disk
resize playbooks read their inventory targets, check the live VM against them,
and refuse unrecognized drift or a memory shrink. There is no automated vCPU
resize playbook yet.

Use `resize-worker.yml` for worker memory and `resize-control-plane.yml` for
control-plane memory. A control-plane memory change requires an explicit
`-e talos_control_plane_resize_approved=true`; it shuts down the single control
plane and interrupts the Kubernetes API until Talos and Kubernetes recover.
The playbook requires the expected cluster, all nodes Ready, Applications
Synced/Healthy with the reviewed watchdog exception above, a same-day off-host
VM backup, an etcd snapshot less than 24 hours old, and enough Proxmox memory
to preserve the 2 GiB host reserve. After
restarting, it verifies Talos health, node readiness, and Application health.

For a control-plane memory resize, update `memory_mib` and
`allowed_memory_mib` in `vars.yaml`, then run:

```sh
just run talos-cluster/snapshot-etcd
ssh pve-g3-1 'vzdump 142 --storage proxmox-backups --mode snapshot --compress zstd'
just run talos-cluster/resize-control-plane -e talos_control_plane_resize_approved=true
```

Use the target node's `host` and `vmid` from `vars.yaml` in the backup
command. Do not use the all-node `backup-now` playbook when only one VM needs a
fresh backup. A disk resize does not relocate node-local PVCs.

### Talos OS upgrade (one node at a time, workers first)

Order: workers first, the single control plane last, so the new image is
proven before touching the only etcd host. Expect API downtime during the
control-plane reboot — there is no control-plane HA.

1. Backups first: a Proxmox snapshot (`backup-now.yml`, or the 02:00 job)
   and an off-host etcd snapshot (`snapshot-etcd.yml`). Confirm Argo
   Applications are Synced/Healthy (subject to the watchdog exception above)
   and all nodes are Ready.
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
   version before the next. Read the schematic from reviewed configuration,
   select the approved target image, and obtain explicit reboot approval before
   issuing any upgrade command.

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
7. Renovate proposes same-minor patch updates to the rebuild pins in
   `vars.yaml`, keeping `talos_version`, `talos_iso_filename`, and
   `talos_iso_sha256` in sync. Review and merge those pin updates separately;
   they do not upgrade live nodes. For a manual OS upgrade, reconcile the pins
   to the installed release after all nodes are verified, regenerate configs
   with the matching `talosctl`, reapply, and review the rebuild inputs.
   Minor upgrades remain manual and must step through each minor. Push only on
   explicit request.

### Kubernetes upgrade (separate from Talos)

A Talos OS upgrade does not upgrade Kubernetes by default. Use a separate
maintenance window and review compatibility for the approved target version.
Run `talosctl upgrade-k8s --to <approved-version> --dry-run` with an explicit
control-plane `--endpoints` address and the intended protected Talos config.

Remove `--dry-run` only after the dry run is clean. The command is sent
to the control plane but upgrades all members.

## Related runbooks

- [Application and platform overview](../README.md)
- [Backups and Homepage restore drill](../BACKUPS.md)
- [Network policies and Pod Security](../SECURITY.md)
