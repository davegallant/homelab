# Kubernetes security and network policy

Review [Cilium values](apps/cilium/values.yaml), workload policy manifests,
namespace labels and Argo AppProjects for intended boundaries. Inspect live
resources to establish enforcement; a tracked deny rule alone is insufficient.

## Pod Security rollout (Kubernetes v1.37)

Restricted `warn` and `audit` are staged on ordinary application namespaces,
pinned to `v1.37`; Baseline enforcement remains while rendered and running
workloads are remediated. Headplane, k8s-readonly, LubeLogger,
Audiobookshelf, BentoPDF, Beszel, Changedetection, Grafana, Homepage, Immich,
Invidious, Jellyfin, Kiwix, Miniflux, Navidrome, Paperless, SearXNG, Seerr, and
Umami enforce Restricted. Confirm live namespace labels before changing this
inventory; the Miniflux restore-drill namespaces are not production workloads.
An unsafe test Pod was rejected by Audiobookshelf's Restricted enforcement;
its existing workloads remained Ready.
LubeLogger runs as UID 1000 and keeps its existing DataProtection keyring on the
application data volume.
Audiobookshelf runs as UID 1000/GID 950, with its existing SQLite database and
metadata on the local PVCs and its NFS library ownership unchanged.
k8s-readonly intentionally mounts its read-only service-account token for
Kubernetes API access. Tailnet Gateway still has Restricted `warn`/`audit`; its
namespace labels are managed through its Argo application.
FlareSolverr and the qBittorrent egress monitor are hardened for Restricted
admission. FlareSolverr uses a non-root init container to copy its
startup-patched Chromium driver into a writable `emptyDir`; the monitor needs
its scoped service-account token to check the protected Cilium policy and Argo
Application. The LinuxServer Speedtest Tracker container now drops all
capabilities except the set its s6
startup and user switch require. RomM and Maloja also use reduced capability
sets tailored to their startup behavior. These containers still start as root,
and their added capabilities are outside Restricted's allowlist, so their
namespaces remain Baseline. qBittorrent's app and bootstrap init container run
as UID/GID 1000 with all capabilities dropped. The init container creates a
user-owned `/run` directory in an `emptyDir` and uses a read-only root filesystem.
The namespace remains Baseline pending recovery verification. Prowlarr's app
also runs as UID/GID 1000 with all capabilities dropped; its non-root init
container prepares `/run` and copies the startup-patched Chromium driver into
writable `emptyDir` volumes. Prowlarr remains Baseline pending recovery
verification.

Lidarr, Radarr, and Sonarr run their pinned images' application binaries
directly as UID/GID 1000, with all capabilities dropped and a read-only root
filesystem. Their startup commands set umask `002` to preserve group-writable
media files; `/tmp` is an `emptyDir`. Their namespaces remain Baseline pending
recovery verification.

Forgejo remains Baseline while its rootful chart init containers and writable
data volume are reviewed. Do not switch it to rootless operation until its
existing data and Velero restore path have been validated under that layout.

This rollout is not complete. Do not raise enforcement in another namespace
until its rendered Pod shapes pass server-side admission, its running workload
and service behavior are verified, and its storage/recovery paths are reviewed.
Restricted admission does not require read-only root filesystems or disable
service-account tokens. Keep applying those workload-level controls, and mount
tokens only for workloads that need Kubernetes API access.

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
