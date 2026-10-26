# qBittorrent egress guardrails

This records the simple w-1 cutover state as of 2026-10-26. The production
gateway policy is deployed and Argo-managed. Torrent start remains a separate
approval gate.

## Production policy

```yaml
apiVersion: cilium.io/v2
kind: CiliumEgressGatewayPolicy
metadata:
  name: qbittorrent
  annotations:
    protected: do-not-delete
  finalizers:
    - homelab.davegallant.ca/protect-egress
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

The policy has no interface selector. Its Argo Application is
`qbittorrent-egress`; automated sync and self-heal are enabled, and pruning is
disabled. This setting applies only to that Application. The policy's separate
AppProject restricts its source and destination.

## Deletion protection

- The policy has annotation `protected: do-not-delete` and finalizer
  `homelab.davegallant.ca/protect-egress`. There is no automatic finalizer
  removal controller. An authorized delete remains Terminating until an
  administrator removes the finalizer; Argo cannot recreate the same name
  while it is Terminating.
- The cluster-scoped maintenance ClusterRole is bound to `admin` and the Argo
  application-controller ServiceAccount. Kubernetes RBAC has no deny rules;
  this scoped role is supplemented by a ValidatingAdmissionPolicy because
  existing wildcard grants otherwise permit deletion.
- The admission policy restricts UPDATE and DELETE of the production and
  fixture policy names to those two identities. The fixture tests passed:
  `qbittorrent:default` DELETE dry-run was denied with 403; `velero:velero-server`
  DELETE dry-run was denied with 403 by admission despite broad RBAC. An admin
  fixture delete remained Terminating until its finalizer was explicitly
  removed; Argo recreated it with a new UID in 2.18 seconds. The fixture App,
  policy and namespace were removed afterward.
- Production DELETE dry-runs by both service accounts were denied with 403.
  The production object was never successfully deleted. Admission type checking
  reported no warnings. A Gotify test notification returned HTTP 200.

These are accidental-deletion guardrails, not a network security boundary.
Cluster administrators can remove the admission policy or finalizers. The
finalizer can delay recovery, and Argo cannot recreate the same name while an
old object is terminating. Gateway-address loss, Cilium or node failure,
router/tunnel failure, policy removal by an exempt admin, and first-packet
enforcement gaps remain separate risks.

## Monitoring

The `qbittorrent-egress-monitor` CronJob runs every five minutes on w-1. Its
service account can read only the production policy and the named Argo
Application. It checks that the policy is present with its protection metadata,
the Argo Application is Synced/Healthy, and the public Mullvad check reports a
Mullvad exit. Failures detected by a running check attempt to send a Gotify message. The Vault-backed
`qbittorrent-egress-alert` Secret is provisioned outside Git.

The monitor ran successfully before it was enabled, and a scheduled run also
completed successfully. It does not read the Cilium BPF map; operators still
verify that map separately. Alert delivery latency has not been measured. This
is detection, not prevention, and the 20-second init delay only orders startup;
it is not a policy-map readiness gate or fail-closed boundary. A job that
cannot be scheduled or started, or a failed alert route, can go unnoticed;
there is no independent missed-run alert.

## Cutover evidence

- LXC 137 was gracefully stopped after Dave approved the timing. It remains
  stopped with its data intact and has not been retired. Its Proxmox veth was
  absent and three raw ARP duplicate-address probes found no claimant for
  `192.168.1.152` before assignment. No router ARP entry existed before
  assignment.
- A runtime `192.168.1.152/32` alias was added to w-1 `ens18`. The alias is
  currently present, but it is not persisted in Talos configuration and may
  be lost on node restart. No Talos configuration was applied and no node was
  rebooted for this cutover.
- Frozen LXC config and K8s copy manifests matched exactly: 1,145 files and
  48,697,652 bytes, with no path/size or mode/ownership differences. The frozen
  source contained zero `.torrent` and zero `.fastresume` files because the
  only torrent had already been deleted. `notify.sh` remained 540 bytes/mode
  0644; `block-malware.sh` remained mode 0750; the pinned Dracula theme is
  present. The old fresh K8s config was retained separately on its PVC.
- The qBittorrent pod is `3/3 Running` on w-1 with zero restarts. Its
  authenticated API reports v5.3.0, zero torrents, `/mnt/torrents`, session
  port 5032, UPnP/DHT/PeX/LSD disabled, and the Dracula alternative WebUI.
  No peer ports, NodePort or LoadBalancer were added.
- The one-off Velero backup `qbittorrent-w1-cutover-20261026131451` completed
  with zero errors and warnings. Its config PodVolumeBackup is 67,411,984
  bytes and Caddy-state backup is 6,199 bytes. The `qbittorrent-daily` schedule
  is Enabled.
- The production Cilium map on w-1 is:

  ```text
  Source IP      Destination CIDR   Egress IP       Gateway IP      Egress Ifindex
  10.245.2.152   10.96.0.0/12       192.168.1.152   Excluded CIDR   0
  10.245.2.152   10.245.0.0/16      192.168.1.152   Excluded CIDR   0
  10.245.2.152   100.64.0.0/10      192.168.1.152   Excluded CIDR   0
  10.245.2.152   192.168.1.0/24     192.168.1.152   Excluded CIDR   0
  10.245.2.152   0.0.0.0/0          192.168.1.152   192.168.1.211   0
  ```

### Packet proof

Captures were simultaneous at pod/pre-NAT, w-1, OPNsense LAN, WireGuard and
WAN interfaces. Evidence is stored in protected temporary directories under
`/var/folders/.../T/` on the operator workstation; captures contain packet
headers only.

| Mode | Result |
| --- | --- |
| Normal production IPv4 TCP and UDP | Verified 2026-10-26. Two HTTPS requests on one TCP socket and one request on a fresh socket returned HTTP 200 with Mullvad exit `23.234.87.92`. Two UDP datagrams used one socket and a third used a fresh socket. Pod, node, router LAN and WireGuard captures showed both protocols; WAN had zero clear probe packets and captured encrypted WireGuard traffic. Capture counts were 48 node, 54 router LAN, 54 WireGuard, 0 plain WAN and 367 encrypted WireGuard WAN packets. Evidence: `/var/folders/n9/mbp934p92f71vd360n8_ps380000gn/T/qbittorrent-normal-proof-8o5xyidb`. |
| New pod with init hold | Production policy map was verified before releasing init. Two TCP requests on one socket and a third on a fresh socket returned HTTP 200 and public exit `23.234.87.92`; two non-DNS UDP datagrams used the same socket and a third used a fresh socket. Pod, node, router LAN and WireGuard captures showed both protocols; WAN had zero clear probe packets and captured encrypted WireGuard traffic. This proves the controlled init-held sequence, not an unheld universal startup guarantee. |
| Missing egress IP, isolated test policy | TCP and UDP packets were visible inside the pod and timed out; no packets appeared at node output, router LAN, tunnel or WAN. The test policy referenced unassigned `192.168.1.253`. |
| No matching gateway, isolated test policy | The map showed egress `0.0.0.0/0`, egress IP `0.0.0.0` and gateway `Not Found`; TCP/UDP timed out and no packets appeared at node output, router LAN, tunnel or WAN. |
| Native IPv6 | A native public IPv6 connect from the pod failed with `errno 101`; the node had no IPv6 default route or global IPv6 address, and Cilium IPv6 is disabled. Userspace tailnet IPv6 is not native public IPv6. |

The normal-mode production TCP/UDP packet gate passed. The isolated drop tests
do not prove production-policy deletion is safe or fail-closed. Explicit WAN
blocking, IPv6 firewalling, production `.152` gateway-down and rule-removal
tests, Mullvad tunnel failure, and production policy deletion behavior remain
unproven. No active WAN leak was observed in the tested modes; this does not
remove the known fallback risk.

Cloudflare and Headscale Mullvad acceptance was not tested in this cutover.

## *arr and peer ingress

Sonarr, Radarr and Lidarr each have an enabled qBittorrent client saved as
`qbittorrent.tail.davegallant.ca:443` with HTTPS. Their queues were empty.
Each app's built-in client test passed for
`qbittorrent-k8s.tail.davegallant.ca:443`; after the production hostname move,
the client records were switched back to `qbittorrent.tail.davegallant.ca:443`
and their built-in tests passed. Protected rollback records
are stored locally in `/tmp/qbittorrent-arr-cutover-20261026/` (directory
0700, files 0600); they are not in Git.

Peer ingress remains open/unresolved: no OPNsense forward exists for 5032 or
6881; only Bedrock UDP 19132 DNAT was found. Mullvad does not support port
forwarding. UPnP remains disabled and neither historical port was published.
Dave has not approved operating without public peer ingress. This is a
degraded seeding limitation and torrent start remains gated on that approval
or a supported ingress arrangement.

## Current stop point

All 34 Argo Applications are Synced/Healthy. The production pod is running on
w-1 with zero torrents. LXC 137 is stopped, not retired; `.152` is assigned to
the w-1 gateway. No new VM or dedicated worker was created, w-1 remains 10
GiB, w-2 was not changed in this cutover, and TrueNAS was not changed here.
The guarded routing and all three *arr endpoint updates are in place, but the
normal-mode TCP/UDP packet gate remains incomplete. Torrent start is stopped
at that gate. Peer-ingress deferral, Talos-persistent alias configuration,
explicit kill switch work, and LXC retirement remain separate decisions.
