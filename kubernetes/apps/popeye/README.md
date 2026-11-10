# Popeye cluster audits

Daily read-only scan at 13:30 UTC. Argo CD owns the CronJob, ConfigMap,
ServiceAccount, cluster RBAC and scoped API/DNS/Pushgateway Cilium policies through the dedicated
`homelab-popeye` project. Namespace provisioning is external: its tracked
Restricted namespace is included in the gitops-secrets namespace loop.

## Reports and permissions

- Popeye v0.22.1 scans PVs, PVCs, ConfigMaps and Services across namespaces.
  These sections cover stale resources without requiring Secret access.
- A Python companion reports Released PVs, claims unreferenced by Pods or
  Deployment/StatefulSet/DaemonSet/Job/CronJob templates, and equal or nested
  local PV paths on overlapping nodes. It checks old claim UIDs independently
  from reused names. Neither container creates, patches or deletes resources.
- RBAC permits only get/list of the enumerated resource kinds. No Secret read,
  exec, logs, mutation or wildcard permissions. The scoped token is required
  by both containers; its Pod Security checker exception is documented.
- No PVC, host mount, new credentials or external ingress. Report output goes
  to container logs and existing Alloy/Loki collection. Job history is bounded
  to three successes and three failures, with a seven-day TTL. Reports are
  diagnostic artifacts, not recoverable application state: no Velero schedule.
- No standalone Popeye HTTP endpoint: this is a batch scanner. Use Job
  status, reports and the Grafana `popeye_scan_stale` freshness alert instead.
  The internal Pushgateway Service holds the latest metrics in memory; it is
  not exposed through the tailnet Gateway. Its Pod has no API token or egress.

Popeye v0.22.1 does not flag Released PVs and its PVC linter only checks Pods;
the companion fills those specific gaps. ConfigMaps consumed dynamically by
operators may still be reported unused. Local path comparison cannot detect
symlink targets, external mounts or aliases outside PV specifications. No
report substitutes for checking backing directories before deletion.

Seven historical application-data PVs retained on 2026-11-10 are explicitly
listed in `chart/files/retained-volumes.json`. They remain visible with their
retention reason, but do not increase `actionable_released_count`. New Released
PVs are not implicitly excluded. Review this list when retiring rollback data.
Shared-path findings stay visible even when intentional. Do not automatically
remove either side of such a pair.

## Deployment and verification

Follow `../argocd/MANAGEMENT.md`. After an explicitly approved push:

1. Provision `namespace.yaml` and apply `../argocd/project-popeye.yaml`.
2. Sync Argo Application definitions, review the Popeye diff, then approve its
   sync without prune or force. No direct Helm mutations.
3. Confirm the CronJob is unsuspended with the intended UTC schedule. Confirm
   `kubectl auth can-i list secrets --as=system:serviceaccount:popeye:popeye`
   and the corresponding PV delete check both return `no`.
4. Verify a real Job completes with exit code zero from both containers. Inspect
   both reports for collection errors and expected sections; findings are not
   scan failures (`--force-exit-zero`), and Job success is not a clean report.
5. Verify the first scheduled run independently from any manual validation Job.
   Then sync Grafana and verify `popeye_scan_stale`. A new CronJob has no successful
   timestamp until its first owned Job succeeds; missing data intentionally alerts.

Read reports:

```sh
kubectl -n popeye get jobs --sort-by=.metadata.creationTimestamp
kubectl -n popeye logs job/<job-name> -c popeye
kubectl -n popeye logs job/<job-name> -c storage-audit
```

The Popeye stream can contain API deprecation warnings before its JSON report.
The companion emits one JSON object with `actionable_released_count`,
`unreferenced_claim_count`, `path_overlap_count` and the detailed candidates.
Reports may contain internal resource names and paths; keep them tailnet-only.
This initial configuration reports findings; it does not notify on every
finding. Grafana monitors missed/failed scheduled scans through CronJob freshness.

## Validation record

A temporary live Job on 2026-11-10 ran both pinned images under Restricted
admission and scoped egress. Both containers exited zero. The companion saw
seven explicitly retained Released PVs, zero unreferenced claims, and 15
shared-path pairs. Those pairs are report findings, not deletion approvals.
The manual validation does not prove the future recurring schedule runs.

## Grafana dashboard and metrics

The provisioned `Popeye cluster audit` dashboard (`/d/homelab-popeye`) uses the
existing VictoriaMetrics datasource. It includes upstream severity/code/linter
panels plus actionable Released PVs, unreferenced claims, shared paths and actual
scan age. Homepage links through `popeye_url`, derived from the existing Grafana URL's
origin (the main Grafana link includes `/explore`). Gatus
already monitors that Grafana front door; no synthetic HTTP endpoint is invented
for the batch scanner.

Popeye pushes its native metrics to the private in-memory Pushgateway; the
companion pushes a separate metric group. Existing annotation-based Alloy
scraping honors their namespace and cluster labels. Alloy's tracked policy adds
only TCP 9091 to the labeled Pushgateway Pods. No new metrics database is needed.
The Pushgateway is deliberately ephemeral: restart it, rerun a scan to repopulate.
`popeye_metrics_stale` checks the actual audit timestamp independently of CronJob
success, so continuously scraping an old report cannot fake a recent audit.

Deployment order after approved push: provision namespace/project, sync Popeye,
sync Alloy's scrape policy, run and inspect a real scan, verify VictoriaMetrics
samples, then sync Grafana. Apply the Homepage external ConfigMap through
`gitops-secrets.yml` and restart Homepage to refresh its subPath mount. Do not
manually edit Argo-owned Grafana ConfigMaps or the existing Alloy policy.

The dashboard is adapted from the upstream v0.22.1
[dashboard source](https://github.com/derailed/popeye/blob/35b554961dcdabfa7aba6bd070673c6c24c70884/grafana/popeye-dashboard.json).
Its license is preserved in `UPSTREAM-LICENSE`.

Live validation used a temporary additive Alloy scrape policy without changing
the existing Argo-owned policy. Alloy reported `up=1`; VictoriaMetrics returned
`popeye_cluster_score{cluster="homelab"}=78`. That temporary policy was removed after
the approved tracked Alloy sync. The dashboard is now installed; see the
[rollout record](../../../operations/popeye-rollout-2026-11-10.md).

Final local validation: full `just lint` passed with 42 Python tests, rendered
Pod Security and backup coverage, Ansible lint, shellcheck and Renovate validation.
The rendered Popeye resources passed server-side dry-run admission. Protected
Homepage/Gatus templates parsed with real inventory/Vault variables; the existing
Grafana URL and raw Homepage placeholder were preserved. All 14 dashboard queries
returned live data from VictoriaMetrics. The dashboard JSON and Grafana alert
provisioning render successfully; installation in running Grafana was verified after the approved source push
and Argo sync. The first timed scan remains independently pending.
