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
are recorded in [SECURITY.md](SECURITY.md).

## 7. Make security expectations enforceable before deployment

**Action:** add manifest rendering and policy checks to review: required digests,
no unintended privileged/host namespace settings, appropriate service accounts,
resource budgets, and expected isolation. Use native admission policies where
sufficient; introduce a policy engine only when it adds needed functionality.
Start in audit mode, with explicit platform exceptions. Scan image vulnerabilities
and prioritize reachable high-impact findings; pinning alone does not patch them.

**Acceptance:** deliberate bad fixtures fail validation; existing workloads and
recovery jobs pass with documented exceptions. Signature verification can follow
when there is a maintained trust policy for the images actually used.

## 8. Reconcile versions, drift, and operational security records

**Action:** reconcile live state with rendered configuration and update stale
records. Verify the actual Kubernetes/Cilium/Talos support matrix against vendor
documentation before upgrades; an observed working pairing is not proof of
vendor support. Finish existing maintenance only after its recorded gates pass.
Keep digest updates, compatibility review, and backup verification coupled.

**Acceptance:** one accurate inventory covers OS, Kubernetes, CNI, proxy mode,
exceptions, and pending gates. Upgrade one node at a time; preserve the existing
stop-on-failure rules and local-PV recovery constraints.

## 9. Detect abuse and resource exhaustion

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
