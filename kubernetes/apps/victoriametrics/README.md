# VictoriaMetrics

VictoriaMetrics runs as a single instance in `monitoring`, pinned to
`k8s-w-1`. The `victoriametrics-data` claim uses local-path with
`volumeType: local`; its bound PV must be verified as type `local` before
copying any TSDB data. The Deployment keeps the upstream v1.154.1 image digest
and 12-month retention from the Grafana LXC.

The ClusterIP Service listens on TCP 8428. Its Cilium policy admits only Alloy
and Grafana. No Gateway route is needed. Alloy remote-writes to the Service;
Grafana's VictoriaMetrics datasource queries it. Velero coverage is validated
with a one-off namespace backup after cutover; no Schedule is declared here.

The Grafana LXC TSDB is retained unchanged as rollback material. Stop its
VictoriaMetrics container before making a frozen copy. Preserve the old TSDB
until the Kubernetes copy, cutover, and Velero backup have been verified.
