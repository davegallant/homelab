# Kiwix on Talos Kubernetes

Migration #4, and the first workload whose data lives on the NAS: the
ZIM library stays exactly where it is on TrueNAS and the pod mounts it
over NFS. Exposure is tailnet-only, mirroring the Homepage pod
(Tailscale sidecar + Caddy with a Cloudflare DNS-01 certificate).

## Source of truth (LXC, pre-migration)

- Host `kiwix` (CT 114, unprivileged, 2 cores / 2 GiB), Compose at
  `/root/docker-compose.yml` on the host.
- Image `ghcr.io/kiwix/kiwix-serve:3.8.2` (digest pinned in
  `chart/values.yaml`), command `*.zim`, data `/mnt/media/kiwix`
  bind-mounted to `/data`, port 8080 on localhost.
- The LXC path `/mnt/media` is a Proxmox bind mount of the host's
  `/mnt/tank/media`; the host mounts `192.168.1.16:/mnt/tank/media/kiwix`
  over NFS4 (see the host /etc/fstab). The cluster PV points at the
  same export directly.
- HTTPS today comes from the `tailnet_caddy` Ansible role; in the
  cluster the Caddy moves in-pod, same certificate story.

## Design

- **Storage is not chart-managed** (`storage.yaml`, applied by the
  playbook): the NFS PV/PVC for the library plus two small static
  local PVs on k8s-w-1 for sidecar state (Tailscale identity 64Mi,
  Caddy cert state 256Mi). The local dirs arrive via .keep entries in
  `cluster/worker.patch.yaml.j2` — machine config only materializes
  them on node **reboot**, so k8s-w-1 must reboot after the patch is
  applied before cutover can mount them.
- **NFS platform dependency:** `apps/nfs-csi` (csi-driver-nfs) must be
  installed and smoke-tested first. Talos has no host NFS tooling;
  the driver carries its own.
- **Backups are manifests-only** (chart schedule `kiwix-daily`): the
  library's protection is TrueNAS snapshots + Drive sync, and the
  Tailscale identity PVC is excluded by name in the pod annotation.
- **Cutover keeps one identity owner:** stage runs with
  `tailscale.enabled=false` (the LXC still owns `kiwix` on the
  tailnet). Cutover stops the LXC stack, creates a one-use Headscale
  preauth key exactly like the Homepage playbook (created on
  `pangolin` via `docker exec headscale`, held only in Ansible
  memory, applied as a Secret, deleted after the identity verifies
  and survives a restart without it), then flips the sidecars on.
- **Verification is content-level:** the playbook lists `/data` in the
  running pod and asserts at least one `*.zim` is visible, fetches
  the app over a port-forward expecting 200 + "Kiwix" in the body,
  and after cutover fetches `https://kiwix.<magicDnsDomain>/` pinned
  to the sidecar's tailnet IP with `--resolve`, expecting 200 +
  "Kiwix".

## Run order

1. `nfs-csi.yml` install, then smoke.
2. Apply the cluster config patch if not yet converged (the .keep
   entries), and reboot k8s-w-1 when Dave approves — required before
   cutover, not before staging.
3. `kiwix.yml` stage → verify.
4. `kiwix.yml` cutover on Dave's go; rollback restarts the LXC stack
   and disables the sidecars.

## Watch items

- kiwix-serve expands `*.zim` via its image shell in `/data`; if the
  pod serves an empty catalog despite files being listed, the arg is
  being taken literally — check the container logs first.
- The NFS volumeAttributes spelling is csi-driver-nfs's contract; if
  the mount fails, reconcile `storage.yaml` against the driver's
  current static-provisioning example before changing anything else.
