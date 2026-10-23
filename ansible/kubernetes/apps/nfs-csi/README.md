# NFS CSI driver (cluster storage platform)

Why this exists: several workloads keep their data on the TrueNAS and
only need it *mounted* — Kiwix's ZIM library first, then the media tier
(Navidrome's music, RomM's ROMs, Audiobookshelf). The LXC pattern was a
Proxmox-host NFS mount bind-mounted into the guest. Kubernetes on
Talos cannot do that: Talos ships no NFS client tooling in the host OS
for the kubelet to call. The upstream `csi-driver-nfs` carries the
tooling inside its own node-plugin pods, which is why it is the
standard answer on Talos.

## Facts this rests on (verified 2026-10-22)

- TrueNAS is 192.168.1.16 and already exports the relevant paths over
  NFS4 — the Proxmox host's /etc/fstab mounts them today:
  `/mnt/tank/media/kiwix`, `/mnt/tank/media/Music`,
  `/mnt/tank/media/romm`, `/mnt/tank/immich`, `/mnt/tank/backups`,
  per-user shares. The cluster reuses the same exports; nothing
  changes on the TrueNAS.
- The driver is installed from its official Helm chart (pinned in
  `vars.yaml`) into kube-system, which is Pod Security exempt on
  Talos — the node plugin is privileged by design (it performs
  mounts).
- v1 is **static provisioning only** (values set
  `storageClass.create: false`). Each consumer ships a static PV that
  points at an existing export, exactly like the Homepage local PVs
  but network-backed. Dynamic provisioning is a later decision for the
  first consumer that needs per-PVC directories.
- `network-policy.yaml` applies a default-deny Cilium policy to the
  controller pods only. The chart shares `kube-system` with DNS and
  other cluster services, so a namespace-wide deny there would be unsafe.
  The privileged node-plugin pods use host networking; their NFS mounts
  are node traffic and are verified with the fresh PVC smoke test below.

## Static PV shape (per consumer)

```yaml
spec:
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: <unique-per-volume>   # e.g. truenas-kiwix-media
    volumeAttributes:
      server: 192.168.1.16
      share: /mnt/tank/media/kiwix
  mountOptions: [hard, nfsvers=4.1, noatime]
```

If a mount fails at install time, reconcile this block against the
driver's current static-provisioning example before improvising — the
volumeAttributes spelling is the driver's contract, not ours.

## Verification

`nfs-csi.yml -e nfs_csi_action=smoke` builds a throwaway namespace,
PV/PVC and pod against the Kiwix export, asserts a `*.zim` listing
comes back non-empty, and tears the whole rig down. A green smoke test
is the platform's definition of working: driver present, export
reachable from a real node, mount semantics sane.

## Backup posture

NFS-backed PV data is **never** Velero filesystem-backed-up: the data's
protection is TrueNAS snapshots and its Drive sync, where it already
lives. Velero schedules for consumers of this driver are
manifests-only, with the data volume named in the
backup-volumes-excludes annotation for explicitness.
