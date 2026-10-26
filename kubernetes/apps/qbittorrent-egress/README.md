# qBittorrent egress guardrails

Prepared for the simple w-1 cutover. Preparation and server-side dry-run
validation do not mean the policy or protection has been deployed or tested.

## Scope

- The separate `qbittorrent-egress` Application reconciles only the production
  CiliumEgressGatewayPolicy. Automated sync and self-heal are enabled; pruning
  is explicitly disabled. Other Applications retain their existing settings.
- The policy uses `egressIP: 192.168.1.152` without an interface selector and
  selects qBittorrent on w-1, excluding LAN, pod, service and tailnet CIDRs.
- The custom finalizer deliberately has no automatic removal controller.
  An authorized delete remains Terminating until an administrator removes
  the finalizer. Argo cannot recreate the same name while it is Terminating.
- Kubernetes RBAC has no deny rules. The scoped maintenance ClusterRole and
  binding are supplemented by a ValidatingAdmissionPolicy because existing
  wildcard grants otherwise permit deletion. Admission restricts UPDATE and
  DELETE of the production and fixture names to the authenticated `admin`
  identity and the Argo application-controller ServiceAccount.
- This is an accidental-deletion guardrail, not a network security boundary.
  Administrators can remove admission protection or finalizers. Node/address,
  Cilium, router, tunnel and initial-enforcement failures remain separate.

## Deployment gates

1. Obtain Dave's specific approval to commit and publish these cutover files.
   The Application source paths must exist in remote main before application.
2. Apply the scoped project and admission/RBAC protection, verify admission
   type checking, then deploy the isolated fixture Application.
3. Test an unprivileged identity's forbidden delete. Also test a privileged
   non-exempt identity with a server-side dry-run, proving admission covers
   wildcard RBAC grants. Test the fixture's finalizer using admin deletion;
   explicitly remove its finalizer and measure Argo recreation with a new UID.
4. Remove the fixture Application without cascading deletion or pruning, then
   delete its policy using admin and explicit finalizer removal. Remove any
   temporary test identities and grants.
5. Complete the approved LXC stop and exclusive .152 ownership checks before
   assigning .152 on w-1 or activating the production routing policy. Keep
   torrents stopped through source-copy, backup, map and packet-evidence gates.
6. Verify production policy ownership, Synced status, finalizer, annotation,
   non-admin dry-run denial and Cilium map. Never successfully delete the
   production policy as a test.

The fixture selects a namespace and label with no workloads. It tests only
object protection and reconciliation, not production egress or fail-closed
behavior. Its Application has no cascading-deletion finalizer.

Disappearance/OutOfSync alert delivery and gateway-map/public-IP checks still
need implementation and verification before the guardrail step is complete.
Publishing these manifests alone does not pass that step or authorize torrent
start, peer-ingress deferral, commits of other files, or LXC retirement.
