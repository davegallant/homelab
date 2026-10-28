# Grafana

Grafana runs on `k8s-w-1` and is exposed through the shared tailnet gateway at
`https://grafana.tail.davegallant.ca/`. Homepage and Gatus retain this URL.
The original Grafana data remains on the Grafana LXC as cutover rollback
material. VictoriaMetrics runs in the `monitoring` namespace and Grafana uses
its ClusterIP Service at `victoriametrics.monitoring.svc.cluster.local:8428`.

Grafana's SQLite database and plugin directory use an annotated local-path
PVC, pinned to w-1. Provisioned dashboards, datasources and alert rules are
in the chart. Grafana credentials and non-provisioned settings are preserved
in the database. Datasource URLs and the Cilium policy must change together
when a backend moves.

The daily Velero schedule excludes Secrets and backs up the data volume. A
pre-backup hook writes a consistent SQLite copy to `grafana-backup.db` on the
volume. During restore, replace `grafana.db` with that copy before starting
Grafana. Verify a completed PodVolumeBackup with nonzero bytes and the
schedule's enabled status. The cutover backup `grafana-cutover-hookfix-20261028`
completed with one successful hook and a 538,848,593-byte volume backup; the
first scheduled run remains to be verified.

The old LXC Grafana process is stopped. Its Headscale node was renamed
`grafana-backend` so Grafana's original name could point to the shared gateway;
Ansible reaches that node by its stable tailnet address with its original SSH
host key alias. Keep the LXC source until rollback is no longer needed.
