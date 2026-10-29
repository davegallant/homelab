# Prioritized homelab hardening guide

Reviewed 2026-10-28. Scope: repository configuration, primarily Talos Kubernetes,
with shared LXC/network controls. No live cluster audit or infrastructure changes
were performed. A checked-in value establishes intent, not live enforcement.
Ranking weighs potential compromise impact, exposure, and effort; it is not a
claim that an exploit or credential leak has occurred.

## Existing strengths

Keep the manual Argo sync gates, application AppProject resource allowlists,
Cilium isolation, version/digest pinning, Vault-rendered external Secrets, and
protected Talos credential directory. Talos and the VM boundary already remove
much of the mutable Linux host surface. These controls are complementary:
AppProject allowlists and image digests do not enforce container security settings
or establish that an image is trustworthy.

## 1. Isolate privileged CI execution — highest priority

**Evidence:** `apps/forgejo-runner/values.production.yaml` sets the chart security
context to privileged and job containers to `network: host`. Its namespace labels
set enforce, audit, and warn all to privileged. Its README still describes a
not-yet-deployed draft and different networking, so deployment status needs checking.

**Risk:** workflow code executes alongside production data on shared workers.
Privileged DinD substantially weakens the pod boundary; Docker host networking
here means the DinD/pod network namespace, not automatically the Talos host.
Unprivileged job containers do not remove the privileged daemon's attack surface.

**Action:** prefer a dedicated runner VM outside this production cluster. Until
then, restrict registration and workflow triggers to trusted repositories and
maintainers, prevent untrusted PR jobs receiving secrets, use short-lived job
credentials, cap concurrency and daemon resources, and inventory runner egress.
A dedicated tainted worker reduces sharing but is not a separate cluster boundary.
Keep necessary privileged enforcement scoped; use baseline/restricted audit and
warn to expose deviations rather than silencing them.

**Acceptance:** inspect rendered and live runner pods, prove a real checkout/job
works, and demonstrate jobs cannot reach unrelated APIs, NAS exports, or production
credentials. Document the actual network mode and trust restrictions.

## 2. Protect secret-bearing backups and test credential recovery

**Evidence:** `BACKUPS.md` warns that Velero resource archives are not encrypted,
but explicitly records `forgejo-daily` including Secrets for runner registration.
VM backups and off-host etcd snapshots also carry sensitive state.

**Action:** inspect the actual schedule and stored archives without printing
Secret data. Prefer reconstructing registration/other Secrets from Vault and
excluding them from resource archives where recovery permits. If inclusion is
required, document and verify encryption of that archive/storage path, tightly
scope Garage credentials, and protect offsite copies and recovery keys separately.
Do not assume Kopia volume encryption encrypts the Kubernetes resource archive.
Verify effective Talos etcd Secret encryption rather than assuming vanilla
Kubernetes defaults apply. Disk encryption and backup encryption solve different
problems; a snapshot can carry decryption material.

**Acceptance:** an isolated restore recovers database data plus Vault-sourced
credentials; backup readers and writers have only necessary permissions. Record
who can decrypt each backup layer and how keys survive loss of the operator Mac.
Rotate credentials if unauthorized backup exposure is established.

## 3. Reduce deployment and administrator blast radius

**Evidence:** `apps/argocd/platform-project.yaml` allows ClusterRoleBindings,
admission policy, namespaces, and many application destinations. The ordinary
`project.yaml` forbids cluster resources, which is a useful existing boundary.
`apps/argocd/values.production.yaml` does not itself establish SSO/MFA or user RBAC.

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

**Evidence:** `cluster/README.md` places nodes on the home LAN.
`../ansible/playbooks/vps/policy.headscale.hujson` grants member devices broad
network access and root SSH to member/tagged nodes. Tagged services already have
more specific ACLs and tests.

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

**Evidence:** `SECURITY.md` describes namespace default deny; Forgejo values still
allow unrestricted `world` egress and host ingress, with specific LAN/service
CIDR denies. This is better than no policy but permits broad internet access.
The documented policy inventory is older than the current application inventory.

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

**Evidence:** `SECURITY.md` documents baseline enforcement and privileged platform
exceptions. Runner audit/warn are also privileged. Existing application values
already use capability dropping and privilege-escalation prevention in places.

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

## 7. Make security expectations enforceable before deployment

**Evidence:** `SECURITY.md` explicitly defers Kyverno on the basis of AppProject
allowlists, baseline labels, and digests. Those controls leave gaps in pod fields,
image provenance, and future policy omissions.

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

**Evidence:** `SECURITY.md` says kube-proxy is enabled and Kubernetes is 1.37.0;
`cluster/README.md` says kube-proxy is replaced and Kubernetes is 1.37.2. The latter
also records mixed Talos versions and a paused worker disk/reboot gate. The runner
README disagrees with its current values.

**Action:** reconcile live state with rendered configuration and update stale
records. Verify the actual Kubernetes/Cilium/Talos support matrix against vendor
documentation before upgrades; an observed working pairing is not proof of
vendor support. Finish existing maintenance only after its recorded gates pass.
Keep digest updates, compatibility review, and backup verification coupled.

**Acceptance:** one accurate inventory covers OS, Kubernetes, CNI, proxy mode,
exceptions, and pending gates. Upgrade one node at a time; preserve the existing
stop-on-failure rules and local-PV recovery constraints.

## 9. Detect abuse and resource exhaustion

**Evidence:** Alloy, Hubble, Grafana alerts, and backup runbooks already exist;
`cluster/README.md` records repeated DiskPressure and single-control-plane risk.
Pod logs are not a substitute for Kubernetes API audit evidence.

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

**Evidence:** `../ansible/tasks/install-docker.yml` already handles Docker's
UFW bypass with DOCKER-USER rules. `../ansible/tasks/config.alloy.j2` uses the
Docker socket; access to that socket is a high-trust capability.

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
