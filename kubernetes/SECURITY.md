# Kubernetes security and network policy

Review [Cilium values](apps/cilium/values.yaml), workload policy manifests,
namespace labels and Argo AppProjects for intended boundaries. Inspect live
resources to establish enforcement; a tracked deny rule alone is insufficient.

## Pod Security rollout (Kubernetes v1.37)

Restricted `warn` and `audit` are staged on ordinary application namespaces,
pinned to `v1.37`; Baseline enforcement remains while rendered and running
workloads are remediated. Headplane, k8s-readonly, LubeLogger,
Audiobookshelf, BentoPDF, Beszel, Changedetection, Forgejo, Grafana, Homepage,
Immich, Invidious, Jellyfin, Kiwix, Lidarr, Maloja, Miniflux, Navidrome,
Paperless, Prowlarr, qBittorrent, Radarr, RomM, SearXNG, Seerr, Sonarr, and
Umami enforce Restricted. Confirm live namespace labels before changing this
inventory.
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
capabilities except the set its s6 startup and user switch require. Its
namespace remains Baseline as a reviewed image exception. RomM now runs both
containers without capabilities, as non-root users, with read-only root
filesystems and explicit writable volumes. Its namespace enforces Restricted.
qBittorrent's app
and bootstrap init container run
as UID/GID 1000 with all capabilities dropped. The init container creates a
user-owned `/run` directory in an `emptyDir` and uses a read-only root filesystem.
The namespace enforces Restricted after an isolated restore recovered 69,524,529
bytes and passed admission with the restored config. The current egress monitor
Job passes Restricted; one failed pre-enforcement Job Pod remains as evidence.
Prowlarr's app
also runs as UID/GID 1000 with all capabilities dropped; its non-root init
container prepares `/run` and copies the startup-patched Chromium driver into
writable `emptyDir` volumes. Its namespace enforces Restricted after an
isolated restore recovered 136,087,005 bytes and passed admission with the
restored config.

Lidarr, Radarr, and Sonarr run their pinned images' application binaries
directly as UID/GID 1000, with all capabilities dropped and a read-only root
filesystem. Their startup commands set umask `002` to preserve group-writable
media files; `/tmp` is an `emptyDir`. Radarr's namespace enforces Restricted
after its isolated config restore recovered 579,598,747 bytes and the restored
app started as UID 1000 with a read-only root filesystem. Sonarr's namespace
enforces Restricted after its isolated config restore recovered 307,684,995
bytes and the restored app returned HTTP 302 as UID 1000 with a read-only root
filesystem. Lidarr's namespace also enforces Restricted after its isolated
config restore recovered 716,627,007 bytes and the restored app returned HTTP
302 as UID 1000. Sonarr media and Lidarr media/music NFS volumes were detached
during their isolated restores.

Speedtest Tracker's 2026-10-31 hardening backup initially failed because the
non-root PostgreSQL process could not overwrite the prior root-owned SQL dump.
The hook now writes a mode-0600 temporary dump and renames it into place. A live
`pg_dump` probe succeeded, and `speedtest-hardening-20261031-retry` completed
with 53/53 items, all three volume backups complete, and no failed hooks.
Speedtest Tracker now has a read-only app root filesystem with explicit `/run`,
`/tmp`, Laravel cache, and Laravel storage volumes. Its small non-root init
container creates Laravel's required storage directories. The dedicated
`speedtest-hardening-20261031-retry` backup restored all three data volumes in
an isolated drill; PostgreSQL recovered, the app read 14,581 results and 2
users, the login page returned HTTP 200, and all three containers were Ready.
The pinned LinuxServer image's s6 startup launches nginx and PHP-FPM masters as
root and uses six additional capabilities; running the full image as non-root
failed because its startup scripts require group switching. Keep the namespace
at Baseline as a reviewed image exception until a maintainable rootless startup
path is available.

RomM's app runs as UID/GID 1000 and MariaDB as UID/GID 999; both drop all
capabilities and use read-only root filesystems. RuntimeDefault seccomp, no
service-account token, and explicit writable `emptyDir` mounts cover app and
database runtime paths. The `romm-recovery-20261031` backup restored in
`romm-drill-20261031-v4`; all four PodVolumeRestores completed with expected
byte counts (config 95, MySQL 191,548,412, Redis 6,905,760, resources
1,217,172,959). The restored app ran as UID 1000 under Restricted and returned
HTTP 200. Production config/resources were changed to group 950 with group
write permission; the TrueNAS library was untouched. Production starts
cleanly, returns HTTP 200, reads 1 user and 373 ROMs at schema
`0153_play_permissions`, saves Valkey RDBs successfully, and UID 1000
write/delete checks passed on config, resources, library ROMs, and assets. An
unsafe privileged Pod was rejected after Restricted enforcement. Authenticated
upload and scan workflows were not exercised because this workspace has no
test-user credential.

Maloja runs its pinned image's application directly as UID/GID 1000, with all
capabilities dropped, a read-only root filesystem, and writable `/data` and
`/tmp` volumes. Before migration, `maloja-hardening-20261031` backed up the
data volume; 61 root-owned files were changed to UID/GID 1000 while the app
was stopped. The recorded path list is kept in the protected local Talos
credentials directory as `maloja-root-owned-20261031.paths`. The isolated
restore recovered 23,903,851 bytes. Because that
backup predates the ownership migration, the same ownership correction was
applied only to the restored test volume. The app then started under Restricted
settings, returned HTTP 200, and all three SQLite databases passed
`PRAGMA integrity_check`. The namespace now enforces Restricted.

Forgejo now uses the rootless image with UID/GID 1000, a read-only root
filesystem, all capabilities dropped, RuntimeDefault seccomp, and no service
account token. An isolated Velero restore recovered 1,022,640,284 bytes; the
rootless app started against the restored SQLite database and returned HTTP
200. All chart init containers passed Restricted admission, an unsafe Pod was
rejected, and the production namespace now enforces Restricted.

## Remaining ordinary namespace gates

Live namespace labels are the source of truth. The following production
ordinary namespace still enforces Baseline while warning and auditing
Restricted:

| Namespace | Current hardening | Remaining gate |
|---|---|---|
| Speedtest Tracker | App root filesystem is read-only; app workers drop to the image's `abc` user. Database and Apprise are non-root. Isolated restore passed: 14,581 results, 2 users, HTTP 200, and 3/3 Ready. | Keep Baseline as a reviewed exception; the pinned image's s6 startup runs root-owned service masters and uses six additional capabilities. Revisit if a maintainable rootless path becomes available. |

Platform namespaces Alloy and Loki also remain Baseline with Restricted
warn/audit; review them separately from ordinary applications. The qBittorrent,
Prowlarr, and Miniflux drill namespaces were removed after successful isolated
recovery checks; Velero restore records remain. Miniflux's v4 restore recovered
499,615,433 bytes, including 24 feeds and 4,192 entries. The restored Miniflux
app passed Restricted admission as UID 65534 with a read-only root filesystem,
all capabilities dropped, RuntimeDefault seccomp, and no service-account token;
its healthcheck returned HTTP 200. Its two local-path PVs remain Released with
the Retain policy, preserving the isolated data. The restored PostgreSQL role
password was reconciled to a test-only credential because database roles are
in the volume backup while external Secrets are excluded. The production
database and credentials were not changed.

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
