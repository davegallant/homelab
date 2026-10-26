# qBittorrent app-build report — 2026-10-26

STOP: app build complete. Torrents NOT started, cutover NOT started.
The production LXC still owns .152; no LXC stop, OPNsense/Mullvad change,
production *arr download-client switch, or node egress-IP assignment occurred.

## Gate resolutions

- Peer ingress / OPNsense forwarding: unresolved, explicitly deferred to cutover.
  No peer Service is published and no final peer port was selected. UPnP is false.
- Image and QBITTORRENT_VERSION both use 5.3.0; API confirms v5.3.0.
- notify.sh: live 540-byte script preserved byte-for-byte as an external Secret,
  mode 0644. Malware script is 0750. AutoRun references retained. No torrent
  state/config/fastresume was copied from the LXC.
- NFS: static CSI PV and RWX claim, server 192.168.1.83, share /mnt/pool,
  subPath torrents mounted at /mnt/torrents, consistent with the shared *arr tree.
  No dynamic NFS StorageClass is needed. Local-path is used only for local state.
- Config: source tree measured 50,884 KiB. New 1 GiB annotated claim is Bound;
  PV pvc-ed80f154-30a0-4687-93e8-c1704885b7f8 is spec.local, not hostPath.
- NFS fsGroup: pod-wide settings removed. Read-only metadata observations:
  /mnt uid=1000 gid=1000 mode=755 ctime=2026-06-30T17:42:30.792312852Z;
  /mnt/.Trash-1000 uid=1000 gid=100 mode=700 ctime=2026-05-18T11:58:26.281931526Z.
  These two paths predate the build; this does not prove whole-export metadata history.
- Tailnet test identity: qbittorrent-k8s, tag:monitored; production name preserved.
  Sonarr is an untagged member. Live member ACL allows the target; actual test passes.
- Secrets: Vault-backed external provisioning via provision.yml, no secret values
  in Git or output. Hash variable is used for bootstrap; separate plaintext
  login variable is used only for login tests. Login/hash offline comparison passed.
- Namespace/NFS objects are hand-applied external resources. Argo adoption TODO;
  they are not falsely described as Argo-owned.

## Application and verification

Application: kubernetes/apps/argocd/applications/qbittorrent.yaml,
homelab project, app-template 5.3.0, manual sync, no prune/force.
Pod qbittorrent-76c9dbbc9f-x2245 is 3/3 Running on k8s-w-1, zero restarts.
All 33 Argo Applications are Synced/Healthy.

WebUI https://qbittorrent-k8s.tail.davegallant.ca returns HTTP 200.
Authenticated login succeeds: HTTP 204 plus valid session, API HTTP 200,
v5.3.0. The original checker incorrectly required an Ok. body.
Direct HTTP Service login returned 401 and is a separate path.
Dracula revision 9020f6eb457087270179beb86d45914d434adb6b and index verified;
API confirms alternative UI path /config/qBittorrent/dracula/webui.
Runtime UPnP, WebUI UPnP, DHT, PeX and LSD are false; torrent count is zero.

Sonarr diagnostic identified HTTP-vs-SOCKS5 protocol mismatch in the probe.
Deployment settings: HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:1055,
NO_PROXY=localhost,127.0.0.1,.svc,.cluster.local.
Application-level proxy settings: proxyEnabled=false, proxyType=http,
proxyHostname empty, proxyPort=8080, proxyBypassLocalAddresses=true.
No production settings were modified. From Sonarr through the HTTP proxy:
WebUI HTTP 200; login HTTP/2 204 with session; version and torrents API HTTP 200.
Sonarr download-client test endpoint returned HTTP 200 for the test hostname.
Production download-client settings before/after were identical.

## Backup evidence

Exactly one one-off backup was created in the successful verification run:
qbittorrent-app-build-20261026033041 — Completed, errors 0, warnings 0.

- qbittorrent-app-build-20261026033041-6k8gx: config, Completed, 18,711,706 bytes.
- qbittorrent-app-build-20261026033041-cp8fn: caddy-state, Completed, 6,198 bytes.

Daily schedule: qbittorrent-daily, Enabled, unpaused, 40 4 * * *, TTL 336h.
First scheduled run is still pending. Downloads and tailnet identity are excluded;
Secrets are recreated externally. Notify-script recovery currently depends on
its preserved LXC source; move that protected source to Vault before retiring LXC.

## Network policy — current manifest, verbatim specification

This is the WebUI-build policy. Internet egress also permits the colocated
sidecars. It is NOT a verified gateway-only/fail-closed policy.

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: qbittorrent-defaultdenynetworkpolicy
  namespace: qbittorrent
spec:
  description: 'WebUI-only build: default deny ingress with DNS, Tailscale/Cloudflare egress. NOT a verified gateway-only or fail-closed policy.'
  egress:
  - toEndpoints:
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: kube-system
        k8s:k8s-app: kube-dns
    toPorts:
    - ports:
      - port: '53'
        protocol: UDP
      - port: '53'
        protocol: TCP
  - toEndpoints:
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: qbittorrent
  - toCIDR:
    - 192.168.1.0/24
    toPorts:
    - ports:
      - port: '41641'
        protocol: UDP
  - toEntities:
    - world
  egressDeny:
  - toCIDR:
    - 10.96.0.0/12
    - 10.245.0.0/16
  endpointSelector: {}
  ingress:
  - fromEndpoints:
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: qbittorrent
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: sonarr
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: radarr
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: lidarr
    toPorts:
    - ports:
      - port: '8080'
        protocol: TCP
  - fromEntities:
    - world
    toPorts:
    - ports:
      - port: '41641'
        protocol: UDP
```

## Egress gateway — DESIGN ONLY, NOT applied

No test IP was newly approved; no EgressGatewayPolicy exists. The cutover
example below must not be applied before LXC stop and IP conflict checks.
Fail-closed behavior remains UNTESTED and unresolved, as documented in README.
No claim is made that an ordinary Internet allow rule becomes fail-closed
when paired with this gateway policy.

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

## Source changes and workspace

- Project destination: https://github.com/davegallant/homelab/commit/6216d546d326cd9b4201333a02246a30bb700ef7
- App build: https://github.com/davegallant/homelab/commit/b757fe910985f6542a667977406d8679c1128c55
- NFS fix: https://github.com/davegallant/homelab/commit/b3c0617aeddf9ad25c82cca22a1d3e7111772257

The user's encrypted Vault edit is intentionally uncommitted and preserved.
No other applications' source files were changed. No production identity cutover,
egress .152 assignment, OPNsense change, or torrent activity was performed.
