# Kubernetes security and network policy

Review [Cilium values](apps/cilium/values.yaml), workload policy manifests,
namespace labels and Argo AppProjects for intended boundaries. Inspect live
resources to establish enforcement; a tracked deny rule alone is insufficient.

## Pod Security rollout (Kubernetes v1.37)

Restricted `warn` and `audit` are pinned to `v1.37`, and ordinary application
namespaces enforce Restricted. Headplane, k8s-readonly, LubeLogger,
Audiobookshelf, BentoPDF, Beszel, Changedetection, Forgejo, Grafana, Homepage,
Immich, Invidious, Jellyfin, Kiwix, Lidarr, Maloja, Miniflux, Navidrome,
Paperless, Prowlarr, qBittorrent, Radarr, RomM, SearXNG, Seerr, Sonarr,
Speedtest Tracker, and Umami enforce Restricted. Confirm live namespace labels
before changing this inventory.
An unsafe test Pod was rejected by Audiobookshelf's Restricted enforcement;
its existing workloads remained Ready.
LubeLogger runs as UID 1000 and keeps its existing DataProtection keyring on the
application data volume.
Audiobookshelf runs as UID 1000/GID 950, with its existing SQLite database and
metadata on the local PVCs and its NFS library ownership unchanged.
k8s-readonly intentionally mounts its read-only service-account token for
Kubernetes API access. Alloy enforces Restricted: its node-local discovery
uses the Kubernetes API rather than hostPath mounts, and it needs its scoped
service-account token for pod logs, node metrics and kubelet scraping.
Tailnet Gateway enforces Restricted. Its userspace Tailscale pod runs as
UID/GID 1000 with a read-only root filesystem, RuntimeDefault seccomp, all
capabilities dropped, and no service-account token. Its local-path Tailscale
identity remains excluded from Velero; the state volume was migrated offline
to UID/GID 1000. Tailscale reports online and a Beszel request returned HTTP
200 through the gateway after the rollout.
FlareSolverr and the qBittorrent egress monitor are hardened for Restricted
admission. FlareSolverr uses a non-root init container to copy its
startup-patched Chromium driver into a writable `emptyDir`; the monitor needs
its scoped service-account token to check the protected Cilium policy and Argo
Application. Speedtest Tracker now runs its app as UID/GID 82 with all
capabilities dropped. RomM runs both containers without capabilities, as
non-root users, with read-only root filesystems and explicit writable volumes.
Its namespace enforces Restricted.
qBittorrent's app
and bootstrap init container run
as UID/GID 1000 with all capabilities dropped and read-only root filesystems.
The app has explicit writable mounts for `/config`, `/mnt/torrents`, `/run`,
and `/tmp`; `/scripts` is read-only. The init container creates a user-owned
`/run` directory in an `emptyDir`. After rollout, writes to `/tmp` and `/config`
succeeded, a write to `/etc` was denied, and the WebUI returned HTTP 200 both
inside the Pod and through the Tailnet Gateway. No torrents were started.
The namespace enforces Restricted after an isolated restore recovered 69,524,529
bytes and passed admission with the restored config. The current egress monitor
Job passes Restricted; one failed pre-enforcement Job Pod remains as evidence.
Prowlarr's app
also runs as UID/GID 1000 with all capabilities dropped and a read-only root
filesystem. `/config`, `/run`, and `/tmp` are explicit writable mounts; its
non-root init container prepares `/run` and copies the startup-patched
Chromium driver into writable `emptyDir` volumes. After rollout, writes to
`/tmp` and `/config` succeeded and a write to `/etc` was denied; the local and
tailnet WebUI returned HTTP 302, and both app containers were Ready. Its
namespace enforces Restricted after an isolated restore recovered 136,087,005
bytes and passed admission with the restored config.

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
The `speedtest-hardening-20261031-retry` backup restored all three data volumes
in an isolated drill; PostgreSQL recovered, the previous app read 14,581
results and 2 users, and the login page returned HTTP 200. The LinuxServer
image's s6 startup needed root and extra capabilities, so it was replaced with
the pinned `ghcr.io/alexjustesen/docker-speedtest-tracker:1.15.1` image. Its
non-root init seeds a writable NGINX config `emptyDir`; Laravel storage and
cache also use explicit writable volumes. s6 requires `/run` to retain the
image's UID ownership, so the app root filesystem stays writable. The app runs
as UID/GID 82 with all capabilities dropped, no privilege escalation, and
RuntimeDefault seccomp; PostgreSQL and Apprise retain read-only root
filesystems. A restored copy read 14,598 results, initialized without pending
migrations, served HTTP 200, fetched Ookla server data, and ran 3/3 under
Restricted. Production now enforces Restricted; all three containers are
Ready, the login endpoint returns HTTP 200, and PostgreSQL contains 14,606
results. An unsafe privileged Pod was rejected by Restricted admission.

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

## Namespace enforcement status

All ordinary application namespaces enforce Restricted. The reviewed privileged
exceptions remain Cilium, Intel GPU, local-path storage, Velero, and the
Forgejo runner; platform namespaces retain their existing policy labels.

Loki's first w1 isolated restore created a large chunk tree. During that restore,
several w1 workloads, including Loki, hit liveness timeouts and restarted. The
worker remained Ready. Probe timeouts had also occurred before the restore, so
the restore likely aggravated existing sensitivity; all affected workloads
recovered. A later restore on w2 completed 1,085,182,436 bytes and all 6 items.
Its only warning was the expected conflict on the generated `kube-root-ca.crt`
ConfigMap. Loki started from the restored data as root and returned `/ready`.

The rootless restore test exposed that the local PV's root-owned tree was not
made group-writable by kubelet's `fsGroup` pass. A temporary migration on the
isolated copy set group 1000 and group-write permissions; UID 10001 Loki then
started with a read-only root filesystem, all capabilities dropped,
RuntimeDefault seccomp, and no service-account token. Its Restricted namespace
rejected an unsafe privileged Pod. Loki accepted a synthetic log push (HTTP
204), returned that entry from a query, and also returned older logs from the
restored backup. The `OnRootMismatch` policy avoids repeating the full
permission scan after the volume root is prepared.

Loki now runs under Restricted enforcement. Its production PVC was migrated
during a controlled stop: Loki data was made group-writable for GID 1000, and
the Tailscale state volume was migrated to UID/GID 1000 to retain its identity.
The production Pod is 2/2 Ready, the Tailscale sidecar is online, and `/ready`
and the labels API respond through the tailnet address. The namespace enforces
Restricted v1.37 and rejects an unsafe privileged Pod.

Before migration, the scheduled daily backup completed with a 1.136 GB live
PVC backup; Velero's one warning concerned an obsolete Succeeded Pod whose
volume was skipped. A separate manual Kopia backup read and uploaded about
1.14 GB, then was canceled when Loki restarted and w1 briefly went NotReady;
metrics-server also timed out scraping that node's kubelet. The canceled
backup is not a recovery point. Loki and w1 recovered, and production migration
used the completed scheduled backup. Probe failures predated the manual backup,
so the extra backup I/O may have aggravated existing w1 sensitivity, but the
available evidence does not establish that it caused the restart or NotReady
period.

Follow-up Restore requests mapped to `k8s-w-2` initially stayed `New`,
including a config-map-only control. Restarting the Velero server unblocked
reconciliation; the control restore and manifest-only Loki restore completed.
The reason the original controller stopped reconciling remains unknown. The
first manifest-only Loki restore omitted the PV resource, so it did not trigger
a PVR. A one-file concurrency restore was canceled at 95,957,782 of
1,085,182,436 bytes after very low throughput; a 1.217 GB ROMM PVR using
default concurrency completed in 87 seconds. The next Loki PVR remained
Prepared until its node-agent restarted; the reason for the stale PVR state is
unknown. The rendered rootless Loki Pod passed server-side Restricted
admission, and an unsafe privileged probe was rejected in a temporary
Restricted namespace.
The qBittorrent,
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
