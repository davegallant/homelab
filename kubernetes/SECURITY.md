# Kubernetes security and network policy

Review [Cilium values](apps/cilium/values.yaml), workload policy manifests,
namespace labels and Argo AppProjects for intended boundaries. Inspect live
resources to establish enforcement; a tracked deny rule alone is insufficient.

## Pod Security enforcement

Ordinary application namespaces enforce Restricted; consult namespace labels
and rendered workloads for the current inventory. Restricted admission does not
require read-only root filesystems or disabled service-account tokens. Apply
those controls separately and mount tokens only for workloads that need API
access. Reviewed exceptions and their reasons are in
[`pod-security-exceptions.yaml`](pod-security-exceptions.yaml).

FreshRSS is the reviewed namespace-scoped `baseline` exception: its upstream
image requires a root startup process to configure Apache, PHP, data
permissions, and its refresh cron, then change Apache workers to `www-data`.
Its pod disables privilege escalation and uses RuntimeDefault seccomp. Runtime
default capabilities remain enabled so Apache can change worker identity.

Workload-specific constraints to preserve during changes and restores:

- Immich PostgreSQL needs a writable root filesystem for its entrypoint.
- Speedtest Tracker's app needs a writable root filesystem for its s6 runtime;
  its backup hook writes a protected temporary dump and renames it into place.
- Alloy, k8s-readonly, and the qBittorrent egress monitor need scoped API tokens.
- qBittorrent and Prowlarr prepare writable runtime directories with non-root
  init containers; Prowlarr and FlareSolverr also need writable driver copies.
- Lidarr, Radarr, and Sonarr use umask `002` for group-writable media files.
- Loki's local data must be group-writable for GID 1000; `OnRootMismatch`
  avoids repeated recursive ownership changes after preparation. Restore I/O
  can affect other workloads on the same worker.
- Older Maloja backups may contain root-owned files and need ownership correction
  on an isolated restored volume before running as UID/GID 1000.
- Database role passwords restored from volume backups may need reconciliation
  with recreated external Secrets; see [backup procedures](BACKUPS.md).

Do not raise enforcement in another namespace until rendered Pods pass
server-side Restricted admission, live service behavior is verified, and
storage recovery is reviewed.

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
