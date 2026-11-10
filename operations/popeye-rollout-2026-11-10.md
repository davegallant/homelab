# Popeye rollout — 2026-11-10

Dave approved publishing local main and deploying Popeye, the Alloy scrape
policy, Grafana provisioning and the Homepage link.

## Deployed and verified

- Popeye, Alloy, Grafana and Homepage Applications are Synced and Healthy.
- Popeye's CronJob is unsuspended at `30 13 * * *`, timezone `Etc/UTC`.
  The owned manual Job `popeye-rollout-20261110` completed; the CronJob reports
  lastSuccessfulTime `2026-11-10T20:39:05Z`. The first timed run is due
  November 11 at 13:30 UTC and has not yet been observed.
- Secret listing and PV deletion remain denied to Popeye's ServiceAccount.
- The tracked Alloy network policy replaced the temporary validation policy;
  the temporary policy is absent.
- Grafana's mounted alert configuration matches source. Its alert and dashboard
  providers reloaded successfully through the admin API. Both Popeye rules are
  healthy and inactive. A real Grafana datasource query returned Popeye data.
- The live dashboard is
  [Popeye cluster audit](https://grafana.tail.davegallant.ca/d/homelab-popeye),
  with 16 panels. All 14 data queries previously returned live VictoriaMetrics
  samples; the application API now confirms the provisioned dashboard.
- Homepage's root and services API return HTTP 200. The services API contains
  the correct resolved dashboard URL, also verified in the running Pod's
  environment. The dedicated `popeye_url` derives Grafana's origin because
  the existing Grafana front-door variable includes `/explore`.

The source URL fix passed full lint, 42 tests, and protected Ansible render
assertions against real inventory/Vault variables. Its tracked restart timestamp
keeps Homepage's live Deployment reconciled after the ConfigMap refresh.

Argo CD's pending chart upgrade was outside this rollout: only the Popeye
Application definition was selectively synced from its parent. Other pre-existing
application drift and the backup watchdog's degraded state were left unchanged.
No node reboot, backup deletion or further storage cleanup occurred.
