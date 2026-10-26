# qBittorrent WebUI build

This is a fresh, empty Kubernetes app on `k8s-w-1`, using app-template
5.3.0 and LinuxServer qBittorrent 5.3.0. It does not replace the live LXC.
No torrent state is copied and no torrent is added. Peers have no published
Service; their final listening/forwarded port remains a cutover TODO. The
source's explicit 5032 setting is omitted rather than choosing between it
and the Compose 6881 mapping. UPnP/NAT-PMP, DHT, PeX and LSD are disabled.
Newly added torrents default to stopped as an additional build safeguard.

## Exposure and credentials

Test URL: `https://qbittorrent-k8s.tail.davegallant.ca`. Userspace Tailscale
forwards HTTPS to loopback Caddy, then WebUI port 8080. It gets its own
one-use registration key with existing `tag:monitored`. Headscale member
devices (including the member-owned *arr identities) can reach that tag.
Do not rename the identity to production while the LXC is live.

`provision.yml` materializes external Secrets with `no_log: true` and stdin,
using Ansible Vault. `qbittorrent_webui_password` remains the PBKDF2 hash;
`qbittorrent_webui_login_password` is used only by the login verification.
Neither credential is committed. The bootstrap Secret is copied only when
the fresh config file is absent; it never overwrites existing app state.
The live notification script is read without printing it and projected from
a Secret at mode 0644. The repository malware script is projected at 0750.
Only scripts are copied, never LXC config, fastresume or BT backup state.

Dracula is downloaded from pinned revision
`9020f6eb457087270179beb86d45914d434adb6b` during bootstrap. A marker prevents
re-downloading it on every restart. No unpinned init image is used.

## Storage and backups

Config uses a new 1 GiB local-path PVC annotated `volumeType: local` before
provisioning. The source config tree was measured at 50,884 KiB. Verify the
new PV has `spec.local`, not `spec.hostPath`, before data operations.

The hand-applied NFS RWX PV/PVC uses `192.168.1.83:/mnt/pool`, matching *arr.
The `torrents` subdirectory mounts at `/mnt/torrents`; no downloads are copied
or deleted. NAS snapshots/offsite protection cover downloads. Config and
Caddy state are opted into Velero; NFS and Tailscale identities are excluded.
The tracked daily schedule is 04:40 UTC, TTL 336h, excluding Secrets. Its first
scheduled backup remains pending until observed Completed with nonzero PVBs.
The requested one-off backup proves volume support, not scheduled coverage.

Namespace and NFS PV/PVC in `storage.yaml` are hand-applied external resources,
not Argo-owned. Adoption is a separate TODO. All other chart resources use
manual Argo sync with no prune or force.

## Deployment

From the repository root, with the intended default kubeconfig:

```sh
ansible-playbook kubernetes/apps/qbittorrent/provision.yml \
  -i localhost, --vault-password-file ansible/.vault_pass
kubectl --context homelab apply -f kubernetes/apps/argocd/applications/qbittorrent.yaml
```

Review and manually sync only `qbittorrent`, without prune or force. Verify
PVC types, readiness, authenticated API, theme, zero torrents, *arr test-only
connectivity through the Tailscale HTTP proxy, and a Completed nonzero Velero PodVolumeBackup.
Provisioning does not rotate an existing Tailscale registration Secret.
An expired unused registration key requires a separately reviewed refresh.
Restore Secrets from Vault and preserve or deliberately re-register the
test identity before evaluating a restored deployment. Keep it pinned to w-1
unless local-volume recovery and relocation are explicitly approved.

## Network policy and cutover gate

The applied Cilium policy defaults ingress to denied and permits WebUI
from selected app namespaces plus Tailscale peer UDP. Egress permits DNS,
same-namespace traffic, direct LAN Tailscale peer UDP, and Internet access
needed by the userspace Tailscale sidecar and certificate renewal. The policy
is pod-scoped: all containers share this access. It is NOT verified fail-closed.
No EgressGatewayPolicy or temporary egress IP is applied by this build.

The following is DESIGN ONLY, not an active manifest. It requires the later
LXC stop/IP-conflict gate and explicit assignment of .152 before application:

```yaml
apiVersion: cilium.io/v2
kind: CiliumEgressGatewayPolicy
metadata:
  name: qbittorrent
spec:
  selectors:
    - podSelector:
        matchLabels:
          io.kubernetes.pod.namespace: qbittorrent
          app.kubernetes.io/controller: qbittorrent
  destinationCIDRs:
    - 0.0.0.0/0
  excludedCIDRs:
    - 192.168.1.0/24
    - 10.245.0.0/16
    - 10.96.0.0/12
    - 100.64.0.0/10
  egressGateway:
    nodeSelector:
      matchLabels:
        kubernetes.io/hostname: k8s-w-1
    egressIP: 192.168.1.152
```

A separate fail-closed design is still UNTESTED and unresolved: allowing
Internet destinations in a Cilium pod policy does not condition that access
on EgressGatewayPolicy existence. An unconditional Internet deny would also
deny gateway-directed traffic and the colocated sidecar. Before torrents or
cutover, choose an enforceable boundary, account for the sidecar and initial
policy propagation window, then prove deletion/failure cannot fall back to
normal node NAT. Do not claim the example above plus the build policy solves
that problem. No production node should be cordoned or rebooted to test it.

Homepage/Gatus production entries stay on the live LXC during this build.

## App-build verification, 2026-10-26

The WebUI-only build passed: pod 3/3 Running on w-1, Argo Synced/Healthy,
WebUI HTTP 200, authenticated API v5.3.0, Dracula active, zero torrents.
qBittorrent 5.3.0 login returns HTTP 204 with a session cookie, not the older
`Ok.` response body. The authenticated API is the login success check.
Direct HTTP Service login returned 401; HTTPS through Caddy succeeded.

Sonarr's port 1055 is an HTTP proxy (`TS_OUTBOUND_HTTP_PROXY_LISTEN`), not
SOCKS5. The failed SOCKS5 probe used the wrong protocol. Sonarr's environment
already configures HTTP_PROXY/HTTPS_PROXY correctly. Using that existing HTTP
proxy, HTTPS returned 200, login returned 204 with a valid session, and the
version/torrents APIs returned 200. Sonarr's test-only download-client API
returned HTTP 200 for the test hostname. A before/after comparison confirmed
production download-client settings unchanged. No production settings changed.

Backup `qbittorrent-app-build-20261026033041` completed with zero errors and
warnings: config PVB 18,711,706 bytes, Caddy-state PVB 6,198 bytes. The daily
schedule is Enabled at 04:40 UTC; first scheduled-run proof remains pending.
See BUILD-REPORT.md for gate results and the verbatim policy manifest.

The pod-wide fsGroup was removed to avoid NFS ownership traversal. The config
claim was subsequently replaced under explicit diagnostic approval; the old
Retain PV remains preserved. Config-field text comparisons alone were not
sufficient to identify a login failure: authenticated HTTPS API requests pass.
Never delete a future config claim just because a legacy credential-key grep
fails. Use the actual authenticated API before concluding credentials are bad.
