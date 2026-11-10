# Restore verification matrix

A successful capture is not proof of an application-consistent restore. Keep
the existing watchdog and coverage checks; add recovery evidence below.

## Common isolation gate

Use the Homepage procedure in `kubernetes/BACKUPS.md` as the resource-restore
reference. Before each drill, record the cluster API, source namespace, backup
name, capture time, selected PVCs and target `<service>-drill-<date>` namespace.
Check available disk space and inodes. Do not restore saved production PV
bindings, live tailnet identities, routes or scheduled producers. Use fresh
local-path PVCs with `volumeType: local`; preserve production claims unchanged.

Review every saved workload before starting it. Block notification, email,
webhook, downloader, automation and public ingress paths. Recreate required
Secrets from protected Vault inputs without logging values. Deny egress by
default, allowing only drill-internal dependencies. Namespace remapping does
not rewrite hardcoded production service URLs; inspect those explicitly.

## Representative drills

| Class | Representative | Required evidence |
|---|---|---|
| PostgreSQL | Immich | Database starts, expected tables and counts exist, recreated credentials authenticate, read-only application login and a known original photo work |
| SQLite | FreshRSS | Offline `PRAGMA integrity_check` returns `ok` on a restored copy, ownership is correct, login works, representative subscriptions and saved articles exist |
| Local state plus NAS | Jellyfin | Local metadata restores, NAS mounts read-only for the drill, known library item opens, no library scanning or destructive jobs run |
| Worker loss | Homepage | Fresh claims on an available worker, no reference to the unavailable node's paths, successful config comparison and HTTP check |

Inspect the application's tracked backup hooks and actual backup artifacts.
For PostgreSQL, select a supported logical-dump or consistent physical recovery
procedure for that database version; do not assume copying a running database
filesystem produces a consistent backup. For SQLite, run integrity checks on
an isolated copy with the expected WAL files or the application's own export.

NAS snapshots and remote copies have their own recovery evidence. Mounting the
current production NAS share proves connectivity, not restoration of NAS data.
Use a snapshot clone or isolated restored dataset to prove that part of recovery.

## Evidence and cadence

Run one representative drill monthly, rotating classes; repeat after changing
storage, backup hooks or database major versions. Record in a protected evidence
location: operator, date, backup age, restore duration, restored volume count,
PodVolumeRestore results, database checks, application checks, recovery point and
cleanup results. Never record passwords, tokens or private document/photo content.
A pending drill remains pending until those checks run; this runbook is not proof.

Clean up only the explicitly named drill namespace and its independently verified
PVs after recording evidence. Confirm production claims and endpoints remain
healthy. Keep failed drill evidence and report the failed gate before changing
the recovery procedure.
