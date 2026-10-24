# Speedtest Tracker on Talos

Argo CD manages Speedtest Tracker from `values.production.yaml`; its
Application is `../argocd/applications/speedtest-tracker.yaml`. Follow the
[release management guide](../argocd/MANAGEMENT.md) for updates and
recovery.

The app, PostgreSQL, Apprise, Tailscale, and Caddy run in one pod. Tailnet
HTTPS is served by Caddy through Tailscale Serve. App configuration,
database, and Apprise data use local-path PVCs pinned to `k8s-w-1`. The
`speedtest-tracker-daily` Velero schedule backs up these three volumes and
writes a `pg_dump` into the database volume before backup. Internet egress
is required for speed tests; LAN and cluster ranges remain denied by the
Cilium policy.

See [backup and restore procedures](../../BACKUPS.md) and [cluster
recovery constraints](../../cluster/README.md).
