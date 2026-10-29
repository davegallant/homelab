# qBittorrent egress guardrails

This records the simple w-1 cutover state as of 2026-10-26. The production
gateway policy is deployed and Argo-managed. Torrent start remains a separate
approval gate.

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

## Before operating

Verify the gateway address is present after node restart, the Cilium BPF map
selects the intended gateway, and TCP/UDP packet captures show tunnel egress
without clear WAN probes. Recheck peer ingress and obtain approval before
starting torrents. Do not infer fail-closed behavior from a successful public
IP check or isolated failure test. Preserve source data until retirement is
explicitly authorized.
