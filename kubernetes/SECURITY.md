# Kubernetes security and network policy

Review [Cilium values](apps/cilium/values.yaml), workload policy manifests,
namespace labels and Argo AppProjects for intended boundaries. Inspect live
resources to establish enforcement; a tracked deny rule alone is insufficient.

## Pod Security rollout (Kubernetes v1.37)

Restricted `warn` and `audit` are staged on ordinary application namespaces,
pinned to `v1.37`; Baseline enforcement remains while rendered and running
workloads are remediated. Headplane, k8s-readonly, Trivy, LubeLogger, and
Audiobookshelf enforce Restricted.
Unsafe test Pods were rejected in the enforced namespaces; their existing
workloads remained Ready. Trivy's operator and generated scan Jobs run under
Restricted; the operator keeps its service-account token for Kubernetes API
access.
LubeLogger runs as UID 1000 and keeps its existing DataProtection keyring on the
application data volume.
Audiobookshelf runs as UID 1000/GID 950, with its existing SQLite database and
metadata on the local PVCs and its NFS library ownership unchanged.
k8s-readonly intentionally mounts its read-only service-account token for
Kubernetes API access. Tailnet Gateway still has Restricted `warn`/`audit`; its
namespace labels are managed through its Argo application.
The qBittorrent egress monitor also needs its scoped service-account token to
check the protected Cilium policy and Argo Application.

This rollout is not complete. Do not raise enforcement in another namespace
until its rendered Pod shapes pass server-side admission, its running workload
and service behavior are verified, and its storage/recovery paths are reviewed.
Read-only root filesystems and API-token mounting remain additional hardening
goals beyond Pod Security Admission.

Keep the reviewed CNI, CSI, Intel GPU, local-path storage, monitoring, Velero,
and privileged Forgejo runner namespaces at their existing scoped policies.
Do not apply Restricted cluster-wide or to `kube-system`.

- Cilium endpoint policies do not isolate host-network workloads or traffic
  inside userspace Tailscale/Newt tunnels. Test those paths separately.
- Scope policies narrowly in shared platform namespaces; a namespace-wide deny
  can disrupt unrelated controllers. Test fresh NFS mounts as node traffic.
- Pod Security exceptions require explicit review. Check container privileges
  separately from namespace admission labels.
- Validate required application traffic and denied LAN/API traffic after policy
  changes, including fresh connections and restarted pods.
- Use Hubble events for endpoint attribution; scrape-target metric labels do
  not necessarily identify flow sources or destinations.

See [Cilium operations](apps/cilium/README.md),
[qBittorrent egress limits](apps/qbittorrent-egress/README.md), and
[hardening guidance](HARDENING.md).
