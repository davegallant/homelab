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
capabilities except the set its s6 startup and user switch require. RomM also
uses a reduced capability set tailored to its startup behavior. These
containers still start as root, and their added capabilities are outside
Restricted's allowlist, so their namespaces remain Baseline. qBittorrent's app
and bootstrap init container run
as UID/GID 1000 with all capabilities dropped. The init container creates a
user-owned `/run` directory in an `emptyDir` and uses a read-only root filesystem.
The namespace enforces Restricted after an isolated restore recovered 69,524,529
bytes and passed admission with the restored config. Prowlarr's app
also runs as UID/GID 1000 with all capabilities dropped; its non-root init
container prepares `/run` and copies the startup-patched Chromium driver into
writable `emptyDir` volumes. Its namespace enforces Restricted after an
isolated restore recovered 136,087,005 bytes and passed admission with the
restored config.

Lidarr, Radarr, and Sonarr run their pinned images' application binaries
directly as UID/GID 1000, with all capabilities dropped and a read-only root
filesystem. Their startup commands set umask `002` to preserve group-writable
media files; `/tmp` is an `emptyDir`. Their namespaces remain Baseline pending
recovery verification.

Speedtest Tracker's 2026-10-31 hardening backup initially failed because the
non-root PostgreSQL process could not overwrite the prior root-owned SQL dump.
The hook now writes a mode-0600 temporary dump and renames it into place. A live
`pg_dump` probe succeeded, and `speedtest-hardening-20261031-retry` completed
with 53/53 items, all three volume backups complete, and no failed hooks.
Speedtest Tracker now has a read-only app root filesystem with explicit `/run`,
`/tmp`, Laravel cache, and Laravel storage volumes. Its small non-root init
container creates Laravel's required storage directories. The web login returns
HTTP 200 and the workload is 3/3 Ready. The s6 supervisor, nginx and PHP-FPM
masters still run as root; running the full image as non-root failed because
its startup scripts require group switching. Restricted admission therefore
still warns on this container, and the namespace remains Baseline pending a
maintainable rootless image path or reviewed exception.

Maloja runs its pinned image's application directly as UID/GID 1000, with all
capabilities dropped, a read-only root filesystem, and writable `/data` and
`/tmp` volumes. Before migration, `maloja-hardening-20261031` backed up the
data volume; 61 root-owned files were changed to UID/GID 1000 while the app
was stopped. The recorded path list is kept in the protected local Talos
credentials directory as `maloja-root-owned-20261031.paths`. The namespace
remains Baseline pending recovery verification.

Forgejo remains Baseline while its rootful chart init containers and writable
data volume are reviewed. Do not switch it to rootless operation until its
existing data and Velero restore path have been validated under that layout.

## Remaining ordinary namespace gates

Live namespace labels are the source of truth. The following production
remaining ordinary namespaces still enforce Baseline while warning and
auditing Restricted:

| Namespace | Current hardening | Remaining gate |
|---|---|---|
| Lidarr, Radarr, Sonarr | App binaries run as UID 1000 with read-only root filesystems; NFS write behavior was checked. | Verify isolated config restores before Restricted enforcement. |
| Maloja | App runs as UID 1000 with read-only root filesystem; SQLite integrity passed after ownership migration. | Verify data recovery before Restricted enforcement. |
| Speedtest Tracker | App root filesystem is read-only; app workers drop to the image's `abc` user. Database and Apprise are non-root. Backup completed; app is 3/3 Ready. | s6, nginx and PHP-FPM masters require root and extra capabilities. Validate an isolated restore; find a maintainable rootless path or keep Baseline as a reviewed exception. |
| Forgejo | Rootful chart remains in use. | Validate the existing data and restore path under a rootless layout before changing the image. |
| RomM | Existing reduced-capability configuration remains. | Deferred at Dave's direction. |

Platform namespaces Alloy and Loki also remain Baseline with Restricted
warn/audit; review them separately from ordinary applications. Temporary
recovery namespaces remain isolated and are not production policy targets:
`qbittorrent-drill-v3-20261031` and `prowlarr-drill-v3-20261031` completed
restores of 69,524,529 and 136,087,005 bytes, respectively. Earlier failed
qBittorrent and Prowlarr drills remain for evidence. The older
`miniflux-drill` and `miniflux-drill-v2` namespaces remain Baseline.

Do not raise enforcement in another namespace until rendered Pods pass
server-side Restricted admission, live service behavior is verified, and
storage recovery is reviewed. Restricted admission does not require read-only
root filesystems or disabled service-account tokens. Keep applying those
workload-level controls, and mount tokens only for workloads that need API
access.

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
