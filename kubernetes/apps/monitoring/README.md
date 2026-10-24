# Cluster monitoring (vitals)

## Current operations

Argo CD manages the production resources. Follow [release management](../argocd/MANAGEMENT.md)
for updates, external Secrets, and recovery. Use the tracked production values
and Application definition for desired state. Do not run Helm mutations against
resources owned by Argo CD.

## Shape

```
node-exporter (DaemonSet)  --\
kube-state-metrics         ---- Alloy (existing DaemonSet) scrapes
kubelet /metrics           ---- in-cluster, remote-writes over LAN
kubelet /metrics/cadvisor --/        |
                                     v
                    VictoriaMetrics on the Grafana host :8428
                                     |
                    Grafana (same host) -> Cluster Vitals dashboard
```

- The three in-cluster workloads are **upstream products installed from
  their official Helm charts**, pinned in `vars.yaml` (vendor charts —
  the Velero exception class). This repo does not hand-maintain
  node-exporter's DaemonSet or kube-state-metrics' RBAC; the charts do.
  The only hand-written manifest is `namespace.yaml` (charts don't
  manage Pod Security labels; node-exporter's hostPath mounts need the
  scoped privileged exception, same pattern as the velero namespace).
- **Alloy** gained a metrics pipeline alongside pod logs
  (`apps/alloy/configmap.yaml.j2`): kubelet + cAdvisor scrapes per node
  (HTTPS, its own ServiceAccount token, `alloy-metrics` ClusterRole),
  node-exporter scraped via pod discovery (instance label rewritten to
  the node name), and an annotation-driven scrape for any Service with
  `prometheus.io/scrape=true` (kube-state-metrics today). Everything
  remote-writes to VictoriaMetrics.
- **VictoriaMetrics** runs on the Grafana host, in the same Compose
  stack as Loki and Grafana (`playbooks/grafana/`). Single-binary store,
  12-month retention, unauthenticated — the host firewall admits 8428
  only from the three Talos node IPs, exactly the Loki posture.
- **Grafana stays off-cluster on purpose** (decided 2026-10-22): the
  watcher does not live on the watched. If the cluster is down, the
  dashboards and the alert path are not. Grafana remains off-cluster so monitoring and alerting stay available during cluster outages.
- **metrics-server** rides along to inspect resource usage with: `kubectl top node/pod` now works.
  Its values carry the standard Talos flag `--kubelet-insecure-tls`.

## Files

- `namespace.yaml` — monitoring namespace with Pod Security labels.
- `vars.yaml` — chart repos and pinned chart versions. Image versions
  and registry-resolved digests are pinned in the per-chart values files.
- `values-node-exporter.yaml`, `values-kube-state-metrics.yaml`,
  `values-metrics-server.yaml` — per-chart overrides (naming,
  placement, sizing, the curated KSM collector set: no secrets, no
  configmaps).
- `../../../ansible/playbooks/talos-cluster/monitoring.yml` — install | verify.
- Grafana side: `../../../ansible/playbooks/grafana/docker-compose.yml` (the
  victoriametrics service), `../../../ansible/playbooks/grafana/provisioning/`
  (datasources + the Cluster Vitals dashboard).

## Run order

1. `apply-alloy.yml` (picks up the metrics pipeline + RBAC).
2. `monitoring.yml` (default install; cluster-side checks only).
3. Grafana playbook (adds VictoriaMetrics + datasource + dashboard).
4. `monitoring.yml -e monitoring_action=verify` (end-to-end: series
   from all three nodes + KSM + cAdvisor present in VictoriaMetrics).
5. `just lint`.

## Pre-flight checklist

- Chart pins in `vars.yaml` still exist (helm repo index / search). If
  one is gone, take the nearest current release of the same chart and
  update the pin in the same change.
- node-exporter's chart names its container port `metrics` — Alloy's
  discovery keep-rule depends on that name. If the rendered DaemonSet
  names it differently, fix the rule in the Alloy config, not the
  chart.
- Kubelet scrape TLS: Alloy verifies the kubelet serving cert against
  the cluster CA. If scrapes fail x509, the pragmatic fallback is
  `insecure_skip_verify = true` on the two kubelet tls_config blocks —
  take it if needed and say so in the report.
- The VictoriaMetrics image in the Grafana compose carries a
  `PIN-DIGEST` marker: resolve the real digest for the pinned tag (and
  confirm the tag exists) before the Grafana playbook runs, or Compose
  fails on purpose.
- After the Grafana playbook: the Loki datasource must behave exactly
  as before (it moved from an entrypoint heredoc to a provisioned
  file), the VictoriaMetrics datasource must test healthy, and the
  Cluster Vitals dashboard must load with data.

## Watch items

- Alloy's remote-write WAL lives on its 256Mi emptyDir state volume.
  If the Grafana host is down for hours, the WAL can fill and Alloy
  will shed metrics (logs are a separate path and unaffected). If that
  ever bites, the fix is a bigger state volume, not a redesign.
- VictoriaMetrics writes many small files like Loki does; the Grafana
  host had a Loki inode scare in Oct 2026 — keep an eye on inode usage
  there as retention fills in.
- kube-state-metrics' ClusterRole is generated by its chart from the
  collectors list. Adding a collector in values is the whole change;
  do not hand-edit the generated RBAC.
