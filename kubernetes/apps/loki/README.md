# Loki migration staging

The chart starts at zero replicas while the data and network handoff are
prepared. Loki is unauthenticated. Do not expose it broadly. The source data
is on the Grafana LXC; its compactor working directory was ephemeral and the
new configuration puts that directory on the data volume. A successful
filesystem backup alone does not prove a consistent restore of a live Loki
store. Prove the backup and restoration approach before cutting over.
