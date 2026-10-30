# Backup watchdog

Daily Velero coverage check, alerting via Gotify. Proof, not just
schedules: a namespace counts as covered only when its schedule's latest
Backup is Completed and fresh AND its PodVolumeBackups are Completed for every
Velero-eligible volume. Reported byte progress must be nonzero; if progress is
absent, a Completed PVB with a snapshot ID is accepted as a successful capture;
Velero can omit byte progress for empty volumes.

## What it checks (in order, per namespace with a Bound PVC)

1. Covered by an enabled Velero Schedule? (includedNamespaces, or a
   schedule with no list = all namespaces; paused schedules do not count.)
2. Latest Backup for that schedule: Completed, and started within 36h
   (schedules are daily; 36h allows long runs without false alarms).
3. PVBs for that backup: no Failed PVB, no explicit 0-byte PVB, and every
   eligible PVC has a Completed PVB with nonzero bytes or, when byte progress
   is absent, a snapshot ID. Eligible = pod annotation
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

## Operations and limits

The tracked manifests and script own scheduling, RBAC, exclusions and alert
routing. Provision the Gotify token from Vault. Review exclusions when storage
or volume names change; an excluded volume is not proof of backup protection.

Validate against live Schedules, Backups, PVCs and PodVolumeBackups, then test
Gotify delivery. Use fixture mode to exercise failed, stale, uncovered, zero-byte
and missing-volume backups, plus clean and deliberately excluded cases. A
fixture pass does not prove the CronJob runs or alerts arrive. Independently
monitor missed executions if that guarantee is required.
