# Released PV review — 2026-11-10

Read-only review of context `homelab`, API `https://192.168.1.210:6443`.
All three expected nodes were Ready. No resources, files or data were deleted.

## Recommendation

- 25 former drill volumes: cleanup candidates. All former namespaces are absent.
- 20 retired Tailscale/Caddy volumes: cleanup candidates. Current application
  workloads no longer run those sidecars.
- 7 former application-data volumes: retain pending a separate rollback decision.
  These contain older Invidious, Immich, Forgejo and qBittorrent state.

All 52 PVs are Released with Retain policy, and all backing directories still
exist on their recorded worker. No path equals, contains, or is contained by
another PV path. No direct application hostPath reference overlaps these paths.
Node-exporter mounts host root read-only for monitoring; that broad observational
mount was excluded from application-consumer classification. Talos directory
listings show directories rather than symlinks. This does not establish content
redundancy, application consistency or safe automatic deletion.

Current PVC names were checked independently from old claim UIDs. In particular,
`qbittorrent/qbittorrent-config` exists again with a different UID and a different
backing path. Never delete that current PVC by its historical name.

Current production application data has completed November 10 volume backups:
Forgejo data, Immich production PostgreSQL, Invidious db-data-local, and
qBittorrent config. That does not prove old rollback data is disposable or that
NAS originals are recoverable. Immich's current library is on NFS, separately
protected; its retained old local library is not the production library path.

## Size measurements

Talos `usage -d 0` was run separately against each exact local directory, with
two concurrent reads and a 35-second timeout. It reports bytes, not a promise
of filesystem space recovered. No NAS or whole-node recursive scan was used.

| Group | Volumes | Measured bytes | Unmeasured volumes |
|---|---:|---:|---:|
| drill | 25 | 2,380,151,937 | 5 |
| sidecar | 20 | 272,843 | 0 |
| application-data | 7 | 1,133,951,025 | 0 |

Five Loki drill scans timed out; their sizes are unknown. The measured drill
total is a lower bound. Preserve old restore results and investigation evidence
when removing drill directories; failed historical Restores do not establish
that current production is broken. No Restore objects were removed.

## Per-volume decisions

Full backing paths, PV names and claim identities are in
[the machine-readable inventory](released-pv-review-2026-11-10.json).

| Former claim | Node | Reported bytes | Decision |
|---|---|---:|---|
| forgejo/forgejo-data | k8s-w-1 | 537,311,267 | Retain; rollback review |
| immich/immich-library-local | k8s-w-2 | 33,462,751 | Retain; rollback review |
| immich/immich-postgres-data-local | k8s-w-2 | 337,793,903 | Retain; rollback review |
| invidious/invidious-db-data | k8s-w-2 | 103,272,221 | Retain; rollback review |
| invidious/invidious-db-rollback-w1-stage | k8s-w-1 | 103,362,333 | Retain; rollback review |
| qbittorrent/qbittorrent | k8s-w-1 | 2,326 | Retain; rollback review |
| qbittorrent/qbittorrent-config | k8s-w-1 | 18,746,224 | Retain; rollback review |
| forgejo-drill-20261031/forgejo-data-local | k8s-w-1 | 553,354,836 | Cleanup candidate |
| lidarr-drill-20261031/lidarr-config-local | k8s-w-1 | 650,384,645 | Cleanup candidate |
| loki-drill/loki-data | k8s-w-1 | unknown (timeout) | Cleanup candidate |
| loki-drill/loki-tailscale-state | k8s-w-1 | 6 | Cleanup candidate |
| loki-rootless-data-drill-w2-20261101/loki-data | k8s-w-2 | 6 | Cleanup candidate |
| loki-rootless-drill-20261101/loki-data | k8s-w-2 | 49,877 | Cleanup candidate |
| loki-rootless-drill-w2-20261101/loki-data | k8s-w-2 | 49,877 | Cleanup candidate |
| loki-rootless-pvr-drill-w1-20261101/loki-data | k8s-w-1 | unknown (timeout) | Cleanup candidate |
| loki-rootless-pvr-drill-w2-20261101/loki-data | k8s-w-2 | unknown (timeout) | Cleanup candidate |
| loki-rootless-pvr-drill-w2-v2-20261101/loki-data | k8s-w-2 | unknown (timeout) | Cleanup candidate |
| loki-rootless-pvr-drill-w2-v3-20261101/loki-data | k8s-w-2 | unknown (timeout) | Cleanup candidate |
| maloja-drill-20261031/maloja-data | k8s-w-2 | 6 | Cleanup candidate |
| maloja-drill-20261031/maloja-data-local | k8s-w-2 | 23,937,556 | Cleanup candidate |
| prowlarr-drill-20261031/prowlarr-config-local | k8s-w-1 | 6 | Cleanup candidate |
| prowlarr-drill-v3-20261031/prowlarr-config-local | k8s-w-1 | 29,962,001 | Cleanup candidate |
| qbittorrent-drill-v2-20261031/qbittorrent-config | k8s-w-1 | 6 | Cleanup candidate |
| qbittorrent-drill-v3-20261031/qbittorrent-config | k8s-w-1 | 55,158,516 | Cleanup candidate |
| radarr-drill-20261031/radarr-config-local | k8s-w-1 | 496,340,884 | Cleanup candidate |
| sonarr-drill-20261031/sonarr-config-local | k8s-w-1 | 243,687,108 | Cleanup candidate |
| speedtest-tracker-drill-20261031/speedtest-tracker-apprise | k8s-w-1 | 6 | Cleanup candidate |
| speedtest-tracker-drill-20261031/speedtest-tracker-apprise-local | k8s-w-1 | 119 | Cleanup candidate |
| speedtest-tracker-drill-20261031/speedtest-tracker-config | k8s-w-1 | 6 | Cleanup candidate |
| speedtest-tracker-drill-20261031/speedtest-tracker-config-local | k8s-w-1 | 11,783,217 | Cleanup candidate |
| speedtest-tracker-drill-20261031/speedtest-tracker-db-data | k8s-w-1 | 6 | Cleanup candidate |
| speedtest-tracker-drill-20261031/speedtest-tracker-db-data-local | k8s-w-1 | 315,443,253 | Cleanup candidate |
| changedetection/changedetection-caddy-state | k8s-w-2 | 6,709 | Cleanup candidate |
| changedetection/changedetection-tailscale-state | k8s-w-2 | 21,952 | Cleanup candidate |
| k8s-readonly/k8s-readonly-caddy-state | k8s-w-1 | 6,682 | Cleanup candidate |
| k8s-readonly/k8s-readonly-tailscale-state | k8s-w-1 | 18,040 | Cleanup candidate |
| lidarr/lidarr-caddy-state | k8s-w-1 | 6,640 | Cleanup candidate |
| lidarr/lidarr-tailscale-state | k8s-w-1 | 18,032 | Cleanup candidate |
| lubelogger/lubelogger-caddy-state | k8s-w-2 | 6,668 | Cleanup candidate |
| lubelogger/lubelogger-tailscale-state | k8s-w-2 | 18,036 | Cleanup candidate |
| maloja/maloja-caddy-state | k8s-w-1 | 6,640 | Cleanup candidate |
| maloja/maloja-tailscale-state | k8s-w-1 | 18,139 | Cleanup candidate |
| prowlarr/prowlarr-caddy-state | k8s-w-1 | 6,654 | Cleanup candidate |
| prowlarr/prowlarr-tailscale-state | k8s-w-1 | 18,032 | Cleanup candidate |
| qbittorrent/qbittorrent-caddy-state | k8s-w-1 | 12,566 | Cleanup candidate |
| qbittorrent/qbittorrent-tailscale-state | k8s-w-1 | 30,034 | Cleanup candidate |
| radarr/radarr-caddy-state | k8s-w-1 | 6,640 | Cleanup candidate |
| radarr/radarr-tailscale-state | k8s-w-1 | 18,032 | Cleanup candidate |
| sonarr/sonarr-caddy-state | k8s-w-1 | 6,640 | Cleanup candidate |
| sonarr/sonarr-tailscale-state | k8s-w-1 | 18,032 | Cleanup candidate |
| speedtest-tracker/speedtest-tracker-caddy-state | k8s-w-1 | 6,723 | Cleanup candidate |
| speedtest-tracker/speedtest-tracker-tailscale-state | k8s-w-1 | 21,952 | Cleanup candidate |

## Cleanup gate

Before a later approved cleanup, refresh resource state and reject newly Bound
PVs, UID changes, new controller references, path overlaps or changed node
placement. Preserve the seven application-data volumes and every current PVC.
Delete only explicitly listed Released PV objects and their approved paths;
never infer data ownership from a former claim name or apply bulk Delete policy.
