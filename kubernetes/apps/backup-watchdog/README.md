# Backup watchdog

Daily Velero coverage check, alerting via Gotify. Proof, not just
schedules: a namespace counts as covered only when its schedule's latest
Backup is Completed and fresh AND its PodVolumeBackups are Completed with
nonzero bytes for every Velero-eligible volume.

## What it checks (in order, per namespace with a Bound PVC)

1. Covered by an enabled Velero Schedule? (includedNamespaces, or a
   schedule with no list = all namespaces; paused schedules do not count.)
2. Latest Backup for that schedule: Completed, and started within 36h
   (schedules are daily; 36h allows long runs without false alarms).
3. PVBs for that backup: no Failed PVB, no 0-byte PVB, and every eligible
   PVC has a Completed nonzero PVB. Eligible = pod annotation
   `backup.velero.io/backup-volumes` lists the volume, or the schedule
   sets `defaultVolumesToFsBackup: true`. A schedule with
   `defaultVolumesToFsBackup: false` is NOT by itself manifest-only:
   a pod `backup-volumes` annotation still makes those volumes eligible
   (audiobookshelf: default false, annotation config-local,
   metadata-local, Completed PVBs exist — Gate 0, 2026-10-27, corrected
   from the original manifest-only shortcut, which would have skipped
   real filesystem backup failures). Only namespaces with NO eligible
   volumes (no annotation in any pod AND no covering schedule
   defaulting to fs backup, e.g. kiwix) skip the PVB check: a
   Completed manifest backup is the proof there.

## What it does NOT alert on (reported in the Job log only)

- hostPath volumes: Velero cannot filesystem-back them up.
- NFS volumes: TrueNAS snapshots + Drive sync protect them, not Velero.
- Namespaces/volumes in `allowlist.json`: intentional exclusions.
  Tailscale/Caddy state is excluded by volume suffix (`-tailscale`,
  `-caddy`, `-tailscale-state`, `-caddy-state`): cloning a live tailnet
  identity in a restore is worse than not backing it up.
- Success: no Gotify message on a clean run. A persistent gap pages
  once a day (12:00 UTC run) until fixed; it does not spam hourly.

## Hosting (why this shape)

- CronJob in the `velero` namespace, project `homelab-platform`, manual
  sync, ServerSideApply + FailOnSharedResource, no prune, no auto-sync.
  No new namespace and no project change: `velero` is already a
  homelab-platform destination, and the platform whitelist already
  allows CronJob, ServiceAccount, Role, RoleBinding, ConfigMap,
  CiliumNetworkPolicy, plus ClusterRole/ClusterRoleBinding (cluster).
- The velero namespace's own default-deny blocks world:443, so the
  watchdog carries its own label-selected CiliumNetworkPolicy adding
  world:443 for watchdog pods only. Cilium policies union per endpoint,
  so the Velero controller (not label-selected) stays restricted.
- RBAC is read-only: velero.io schedules/backups/podvolumebackups and
  core PVCs/PVs/pods/namespaces, get/list/watch only. No Secret read.
- Gotify token: Vault-provisioned Secret `backup-watchdog-gotify`
  (key `token`, dedicated app token, NOT the Argo token), mounted as
  env, never in Git. The Secret is NOT Argo-managed (homelab-platform
  allows Secret, but Vault is the source of truth, same pattern as
  `argocd-caddy` in gitops-secrets.yml).
- Schedule: `0 12 * * *` UTC (08:00 EDT). After the 03:00-05:00 UTC
  backup window, with buffer for long runs, so alerts arrive in the
  morning, not overnight.
- Script: stdlib-only Python, in-cluster API via ServiceAccount token
  (no kubectl, no jq). Fixture mode (`WATCHDOG_FIXTURE_DIR`) runs the
  same logic against JSON lists for local testing.

## Known limits (executor must verify live, not assume)

- Live schedules are the source of truth. Only custom charts
  (homepage, kiwix, bentopdf, searxng, miniflux) and forgejo-backup
  carry Schedule manifests in Git; app-template schedules are not
  found as files in this repo, so the watchdog reads live Schedules
  via the API. Git-managing every schedule is separate future work,
  not this item.
- PVB-to-PVC mapping uses pod volume names. If a pod's volume name
  differs from its PVC claim in a way the script does not expect, the
  first live run will show it as a missing-PVB gap — investigate that
  gap before allowlisting it.
- CronJob image is pinned to Python 3.13.18 and a registry digest.
  The pinned image's standard-library imports were verified locally.

## Test evidence (logic, not live)

Fixture run (2026-10-27, Tux VM): 9 namespaces, expected 5 gaps
(failed backup, stale backup, uncovered, 0-byte PVB, missing PVB)
and 0 false positives for ok / manifest-only / allowlisted /
hostPath-only namespaces; clean-fixture run exits 0 with no gaps.
Live verification (schedules, PVCs, PVBs, RBAC, Gotify delivery) is
the executor's Gate 1-3 work, not claimed here.
