# Prioritized homelab hardening guide

Use this as a review checklist, not a deployment or live-state inventory.
Configuration establishes intent; validate enforcement and recovery before
closing an item. Prioritize by exposure and impact in the current environment.

## Existing strengths

Keep the manual Argo sync gates, application AppProject resource allowlists,
Cilium isolation, version/digest pinning, Vault-rendered external Secrets, and
protected Talos credential directory. Talos and the VM boundary already remove
much of the mutable Linux host surface. These controls are complementary:
AppProject allowlists and image digests do not enforce container security settings
or establish that an image is trustworthy.

## 1. Contain privileged in-cluster CI execution — highest priority

**Risk:** the runner and privileged DinD execute on a worker shared with
production workloads. Privileged DinD substantially weakens the pod boundary;
Docker host networking here means the DinD/pod network namespace, not
automatically the Talos host. Unprivileged job containers do not remove the
privileged daemon's attack surface.

**Action:** keep the runner in this cluster. Treat privileged DinD as a reviewed
exception. Restrict registration and workflow triggers to trusted repositories
and maintainers, prevent untrusted PR jobs receiving secrets, use short-lived
job credentials, cap concurrency and daemon resources, and inventory egress
from both the runner pod and DinD job containers. Review tracked runner values
and network policy against live state. A dedicated tainted worker would reduce
sharing but would not create a separate cluster boundary.

**Acceptance:** inspect rendered and live runner pods, prove real trusted
workflows complete checkout and execution, and demonstrate jobs cannot reach
unrelated APIs, NAS exports, node management addresses, or production
credentials. Verify the actual network mode and trust restrictions in Forgejo.

**Progress (2026-11-01):** the live Cilium policy is synced and healthy. It
allows internal Forgejo polling and TCP 443 to the explicit workflow hostnames
in `apps/forgejo-runner/policy/network-policy.yaml`; DNS requests are limited to
those names plus resolver search suffixes and the Forgejo service. A DinD
container reached approved `www.gasbuddy.com`, while unlisted
`www.example.com`, its DNS lookup, and direct public IP `1.1.1.1` were blocked.
Hubble previously recorded a policy drop when both the runner and a DinD job
tried to reach the Kubernetes API. The runner pod has no service-account token
volume. The latest restricted-policy runs succeeded for
[rfd-notify-cron](https://forgejo.davegallant.ca/dave/rfd-notify-cron/actions/runs/52260)
and [gaswatch](https://forgejo.davegallant.ca/dave/gaswatch/actions/runs/1325).

The instance-wide runner registration was replaced with one scoped to user
`dave`. This includes all repositories Dave owns, so new repositories still
need workflow review. The current private workflow repositories have no
collaborators, do not use pull-request triggers, and registration is disabled.
Their external actions are SHA-pinned, and the rfd-notify push trigger is
restricted to `main`.

The full scheduled backup `forgejo-daily-20261101144323` completed with both
Forgejo namespaces, Secrets, and runner data included. Its full restore has
not been tested. A separate Secrets-only snapshot was restored into an isolated
namespace; both runner Secret objects matched the live Secret data exactly.
That drill namespace and temporary backup were deleted. The restored Secret
was not used to start a runner, and fresh registration recovery has not been
exercised. Keep Secrets in backups until the remaining recovery checks pass.

## 2. Protect secret-bearing backups and test credential recovery

**Progress (2026-11-01):** all 28 Velero `BackupRepository` resources report
`Ready`. The 64-character Kopia password from Ansible Vault matches the live
`velero-repo-credentials` Secret. Existing isolated restore drills have read
Kopia-backed volumes successfully. A Secrets-only backup restore recovered
`forgejo-runner-config` and `forgejo-runner-configfile` into an isolated
namespace; their data matched the live Secret objects exactly. The temporary
namespace and snapshot were removed after verification. The full scheduled
backup `forgejo-daily-20261101144323` completed with both Forgejo namespaces,
Secrets, and `runner-data` included. Full backup restore and
fresh-registration-to-chart recovery remain untested. This confirms the
current Kopia credential works, but the history of any password migration and
the encryption/retention of off-site copies still need verification.

**Action:** keep the shared Kopia password in Vault and do not replace its
Kubernetes Secret by itself. Before any future credential change, rehearse
against an isolated repository copy, verify a restore, and take a fresh
backup. Verify Drive copy encryption and retention, Garage key permissions,
and offsite recovery-key access. Keep Secrets included in `forgejo-daily` until
the fresh-registration-to-chart recovery path is proven; do not mistake Kopia
volume encryption for encryption of Velero's Kubernetes resource archive.
Talos `secretbox` is effective for API Secrets in etcd, but etcd and VM
snapshots still carry sensitive state and need the Talos cluster credentials
to recover them.

**Acceptance:** an isolated restore validates Kopia-backed data, Forgejo
database data, and Vault-sourced credentials. Test fresh runner registration
against the deployed chart before excluding Forgejo Secrets.
Backup readers and writers have only necessary permissions. Record who can
decrypt each backup layer and how keys survive loss of the operator Mac. Rotate
credentials if unauthorized backup exposure is established.

## 3. Reduce deployment and administrator blast radius

**Progress (2026-11-01):** none of the 45 current Applications used Argo CD's
built-in `default` project. It now denies all repositories, destinations, and
resource kinds, and the Ansible project playbook guards against future use.
All 45 Applications remained Synced and Healthy after the change. The
Argo CD Redis Pod now disables service-account token automount; the new Pod
has no projected API token, and Argo remains Synced and Healthy. The
[read-only API proxy](apps/k8s-readonly/README.md) returned pod logs and
persistent volumes through its tailnet route and denied `/api/v1/secrets` with
403. Its ServiceAccount can get `pods/log`, but cannot read Secrets or create
Pods, exec, attach, or port-forward. Log text may still contain credentials if
an application writes them. Argo CD still has only its built-in full-admin
login; routine least-privilege identities and MFA remain to review.

**Action:** separate narrowly scoped platform projects from application projects;
remove unnecessary application destinations from the platform project. Review
who can change Applications, AppProjects, repository credentials, namespace
labels, and cluster bindings. Use named routine identities with least privilege,
reserve admin kubeconfig/Talos credentials for maintenance, and protect remote
repository and deployment accounts with MFA. Check the read-only API proxy's
actual verbs and resource scope, including logs and sensitive ConfigMaps.

**Acceptance:** permission checks demonstrate routine identities cannot read
Secrets, create privileged workloads, bind cluster-admin, or alter admission.
Retain tested emergency access before restricting administrators.

## 4. Close management-plane and tailnet lateral paths

**Progress (2026-11-01):** the live Headscale database policy contains the same
broad member rules as the checked-in policy. It allows every
`autogroup:member` device to reach
all Tailnet IPs and ports, and permits those member devices to use Tailscale
SSH as `root` on both member and tagged nodes. Tagged-service ACL tests cover
several restricted sources, but they do not narrow member access. The live
cluster API Service is ClusterIP; the Tailnet Gateway is a LoadBalancer on
`192.168.1.185:443`, and the control-plane node is `192.168.1.210`. No
CiliumHostPolicy CRD is installed; the only CiliumClusterwideNetworkPolicy is
`tailnet-gateway-entry`. A safe Tailnet ACL reduction still needs a verified
mapping of Dave’s administrator devices so routine member access and root SSH
can be narrowed without cutting off recovery. A TCP probe from
`hephaestus` (`192.168.1.165`) reached the control-plane Kubernetes API,
Talos API, kubelet, and etcd ports, plus both workers’ Talos API and kubelet
ports. This confirms the current admin-device path; it does not establish what
other LAN clients can reach.

**Action:** separate administrator devices from ordinary member clients; narrow
root SSH and management destinations. Verify LAN/router/Proxmox firewall rules
for Kubernetes API, Talos API, kubelet, etcd, NFS, and Cilium overlay traffic.
Permit node-to-node dependencies and designated administrators explicitly.
Pod policy does not by itself isolate host-network services or the Talos API.
Audit Gateway routes and application authentication: permission to reach shared
HTTPS port 443 is not authorization to one hostname behind that gateway.

**Acceptance:** test from an admin device, ordinary LAN client, member device,
and restricted tagged service. Required operations succeed; unauthorized
management connections fail. Keep recovery console access during rollout.

## 5. Tighten Cilium policy beyond namespace isolation

**Progress (2026-11-01):** the live cluster has 81 namespace Cilium policies
covering 37 namespaces. All 31 namespaces enforcing Restricted Pod Security
have namespace-scoped policy coverage. The only active pod namespaces without
namespace Cilium policies are `intel-gpu` (device-plugin DaemonSet) and
`tailnet-gateway` (Tailscale fronting pod); both are platform components and
need explicit egress review. Fourteen namespaces have at least one egress rule
to the `world` entity. Most such rules specify ports, but qBittorrent's
namespace policy has an unrestricted `world` egress rule. Its own build record
says gateway-only and fail-closed egress are unverified, and the README gates
torrent startup on that review; the pod currently has zero torrents. A fresh
monitor job passed its policy, Argo health, and Mullvad-exit checks, and a
direct request from the qBittorrent pod also reported a Mullvad exit. The
packet proof did not run: SSH authentication to `root@opnsense` failed at the
capture-readiness gate, before any probe traffic. Thus normal egress is
verified, but fail-closed behavior is not.

**Action:** compare every live endpoint/namespace with rendered policy coverage.
Replace broad internet permissions where feasible with required ports and
reviewed destinations. Separate app, database, and proxy permissions instead of
allowing all same-namespace communication. Review IPv6, alternate private ranges,
node addresses, and sidecar proxy paths; CIDR denies are not a complete identity
boundary. Treat Cilium host policy as a separate, carefully tested change.

**Acceptance:** real application API calls, DNS, backup, and webhook tests pass;
negative probes to unrelated namespaces, node management, NAS, and unwanted
internet destinations fail with Hubble evidence. Do not rely on the dashboard
root responding or the presence of a policy object.

## 6. Move ordinary workloads toward Restricted Pod Security

**Action:** inventory rendered containers and init containers. Start Restricted
warn/audit on ordinary application namespaces, then fix violations and enforce
per namespace. Prefer non-root users, no privilege escalation, drop ALL
capabilities, RuntimeDefault seccomp, and read-only root filesystems with explicit
writable volumes. Disable service-account token mounting for apps without API
needs. Preserve reviewed CNI, CSI, GPU, and backup exceptions; do not apply a
blanket setting that prevents those components starting.

**Acceptance:** rendered and running pods satisfy the intended policy; an unsafe
test pod is rejected in ordinary namespaces. Verify uploads, media processing,
database startup, and restores under the new filesystem/user settings.

**Status (2026-11-01):** all ordinary application namespaces now enforce
Restricted, including Speedtest Tracker. Its restored database started and
retained all results, its login page and Ookla server lookup worked, and an
unsafe Pod was rejected. The app runs non-root with all capabilities dropped;
its root filesystem remains writable because the image's s6 startup requires
`/run` to retain UID 82 ownership. Read-only root filesystems remain in place
for its database and Apprise containers. Other app-specific functional checks
are recorded in [SECURITY.md](SECURITY.md). A live audit checked 36 Running
Pods in Restricted namespaces. The only findings were the documented API-token
needs of Alloy and the read-only API proxy, plus writable-root requirements for
Immich PostgreSQL and Speedtest Tracker; the Alloy exception is recorded in
`pod-security-exceptions.yaml`.

## 7. Make security expectations enforceable before deployment

**Progress (2026-11-01):** `just lint` renders all Argo applications whose
namespaces enforce Restricted Pod Security, then checks every rendered
container and init container for the requested hardening controls and requires
both a version tag and a SHA-256 digest on each image. Remote Helm
charts are rendered at their pinned chart versions; local charts and Kustomize
sources are rendered from the checkout. Exact remaining exceptions and their
reasons live in `pod-security-exceptions.yaml`; stale exceptions also fail the
check. Four checker fixtures pass, including a deliberately violating Pod and
platform exception cases. Lint also validates backup coverage for ordinary
applications and the explicitly backed up `monitoring` platform namespace.
This checkout has no tracked GitHub or Forgejo workflow definitions, so these
checks are local and are not shown to run automatically on changes.

**Action:** extend the local checks to cover unintended privileged/host namespace
settings, appropriate service accounts, resource budgets, and expected isolation.
Use native admission policies where sufficient; introduce a policy engine only
when it adds needed functionality. Start in audit mode, with explicit platform
exceptions. Scan image vulnerabilities and prioritize reachable high-impact
findings; pinning alone does not patch them.

**Acceptance:** deliberate bad fixtures fail validation; existing workloads and
recovery jobs pass with documented exceptions. Signature verification can follow
when there is a maintained trust policy for the images actually used.

## 8. Reconcile versions, drift, and operational security records

**Progress (2026-11-01):** all 45 live Argo Applications are Synced and
Healthy. The three nodes consistently report Kubernetes 1.37.2, Talos 1.14.3,
and containerd 2.3.7; Cilium is pinned at 1.20.4. The checked-in cluster
variables still specify Talos 1.14.1 and its ISO, so desired upgrade inputs
and live state differ. Sidero's [Talos 1.14 support matrix](https://docs.siderolabs.com/talos/v1.14/getting-started/support-matrix)
includes Kubernetes 1.37 and Proxmox. Cilium 1.20.4's [Kubernetes support
matrix](https://docs.cilium.io/en/stable/network/kubernetes/requirements/)
guarantees e2e testing through Kubernetes 1.36; its documentation says
compatibility with newer Kubernetes
versions depends on Kubernetes backward compatibility. Thus Talos 1.14.3 is
within its published matrix, while the Kubernetes 1.37.2/Cilium 1.20.4 pairing
is not explicitly e2e-guaranteed by Cilium.

**Action:** reconcile live state with rendered configuration and update stale
records. Verify the actual Kubernetes/Cilium/Talos support matrix against vendor
documentation before upgrades; an observed working pairing is not proof of
vendor support. Finish existing maintenance only after its recorded gates pass.
Keep digest updates, compatibility review, and backup verification coupled.

**Acceptance:** one accurate inventory covers OS, Kubernetes, CNI, proxy mode,
exceptions, and pending gates. Upgrade one node at a time; preserve the existing
stop-on-failure rules and local-PV recovery constraints.

## 9. Detect abuse and resource exhaustion

**Progress (2026-11-01):** the three nodes are Ready, with MemoryPressure and
DiskPressure false; current memory use is 54–71%. All regular containers in
Restricted namespaces have CPU and memory limits; the remaining gaps there
were five init containers without CPU limits, three of which also lacked memory
limits. The Forgejo, qBittorrent, and Speedtest Tracker gaps are fixed and
rolled out Healthy. A subsequent live audit found the SearXNG cache init
container, absent from the earlier inventory; it now has explicit limits and
rolled out Healthy too. The current live audit found no missing CPU or memory
limits across 36 Running Pods in Restricted namespaces. `just lint` enforces
both limits on rendered Restricted workloads. The qBittorrent egress monitor
init peaked below 1m CPU in the retained three-day metrics window; a 10m limit
is now set, and its next scheduled job completed with the expected policy,
Argo, and Mullvad checks. The cluster has no ResourceQuota or LimitRange
objects. A live audit initially found 49 platform container/init-container
entries missing at least one limit across 36 Running Pods. Three-day p95 usage
was reviewed before making targeted changes. The local-path provisioner used
0.4m CPU and 31 MiB memory at p95; it now has 250m and 256Mi limits, reapplied
by the install playbook. Its PVC smoke test provisioned a volume, read a marker
from a second Pod, and confirmed Delete-policy teardown removed the volume.
Argo CD's missing limits were also set from measured p95 usage: application
controller 47m/434Mi, repo server 79m/102Mi, notifications 2m/103Mi, Redis
3m/13Mi, and server 2m/116Mi for CPU/memory. Argo CD rolled out Healthy, and
all 45 child Applications remained Synced and Healthy. NFS CSI sidecars were
capped at 100m CPU and its NFS containers at 250m after three-day maxima stayed
below 14m CPU and 53 MiB memory; all three node plugins and the controller
rolled out Ready. Cilium operator, Hubble relay, and UI CPU limits were set from
p95 usage (10m, 1m, and under 1m); their Deployments rolled out Healthy without
restarting Cilium agents. The latest live audit has 24 platform entries still
missing at least one limit, in Cilium agents/Envoy/init containers, CoreDNS and
control-plane static Pods, and Velero. These CNI, control-plane, and backup
workloads remain individually reviewed; they do not receive blanket limits.
Grafana has alerts for node memory, `/var` fullness,
restart bursts, and crash loops. The daily `backup-watchdog` completed
successfully today, but no independent missed-run alert or inode-pressure alert
was found in the tracked configuration.

**Action:** verify effective API audit policy and export useful authentication,
Secret-access metadata, RBAC, admission, exec, and policy-change events without
logging secret bodies. Alert on failed backups, disk/inode pressure, certificate
expiry, and unexpected privilege changes. Add measured requests, limits,
ephemeral-storage budgets, and namespace quotas; include DinD consumption.
Keep Loki capacity/inode checks before increasing ingestion.

**Acceptance:** generate a harmless denied operation and verify the event/alert;
rehearse a database restore and node loss. Control-plane HA is a later resilience
investment: three control planes on only two physical hosts still share failure
risks and require a quorum-aware placement plan.

## 10. Apply the same boundaries to remaining LXCs

**Progress (2026-11-01):** the tracked Compose files contain no
`privileged: true`, Docker socket mounts, or explicit device mappings. Host
networking is used by primary and secondary AdGuard, Gatus, and UpSnap; UpSnap
adds `NET_RAW`. The VPS Gerbil service adds `NET_ADMIN` and `SYS_MODULE` for
its reviewed tunnel role. This is a source inventory only; it does not prove
the live containers or Proxmox LXC privilege settings match.

**Action:** preserve the Docker firewall block and test it externally after
Docker/UFW upgrades. Prefer per-source/per-port exceptions over widening all
published ports. Inventory privileged containers, host networking, Docker socket
mounts, and writable NAS access; remove unnecessary access. A read-only socket
mount does not turn the Docker API into a read-only API. Verify unprivileged LXC
configuration at Proxmox, host patching, backup isolation, and root SSH boundaries;
these cannot be established from service Compose files alone.

**Acceptance:** unauthorized LAN/tailnet clients cannot reach published services;
needed service paths and log ingestion still work, and a representative LXC can
be restored without exposing production identities.

## Rollout discipline

Implement one boundary at a time, with a backup and explicit success/negative
checks. Verify the API server and expected nodes before mutations. Keep work on
local main; pushing and live application are separate authorized operations.
Use Argo for its owned resources and Ansible for external Secrets/infrastructure.
A failed gate stops that step; preserve evidence and completed work. This guide
does not authorize deployments, rotations, or reversals.

## Reference guidance

- [Kubernetes security checklist](https://kubernetes.io/docs/concepts/security/security-checklist/): least privilege, network isolation, and gradual Restricted adoption.
- [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/): exact Baseline and Restricted requirements.
- [Secret handling practices](https://kubernetes.io/docs/concepts/security/secrets-good-practices/): access, encryption, and audit considerations.
- [Cluster recovery constraints](cluster/README.md), [backup procedures](BACKUPS.md), and [current security record](SECURITY.md).
