# Grafana migration

Grafana is being migrated from the Grafana LXC to a single replica on
`k8s-w-1`. Loki and VictoriaMetrics stay on the LXC for the first phase.
The existing Homepage and Gatus entries retain the production tailnet URL.

The chart initially sets replicas to zero so the stopped Grafana data can be
copied into the annotated local-path PVC before startup. Preserve the source
on the LXC as rollback material. The Grafana database is SQLite; never copy a
running database as the cutover source. Provisioned dashboards and alerts are
in the chart; datasource URLs point to the LXC LAN address.

Velero's daily schedule excludes Secrets and backs up the data volume. A
pre-backup hook writes a consistent SQLite copy to `grafana-backup.db` on that
volume. During restore, replace `grafana.db` with that copy before starting
Grafana. Recreate external secrets if any are introduced. Verify a completed
PodVolumeBackup with nonzero bytes and the schedule's enabled status.

Before cutover, verify datasource access, the gateway route, the TLS path,
and the Grafana API. The LXC's existing Grafana process and tailnet identity
must be handled before moving the production hostname. Loki and VictoriaMetrics
must remain reachable from all existing senders.
