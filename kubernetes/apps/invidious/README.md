# Invidious on Talos

Argo CD manages the workload from `values.production.yaml`; the
Application is `../argocd/applications/invidious.yaml`. Use the
[release management guide](../argocd/MANAGEMENT.md) for updates and
recovery.

The app, companion, PostgreSQL, and Newt run in one pod. Public access
uses the existing Pangolin route through Newt. Database state is stored
on a local-path PVC and included in the `invidious-daily` Velero backup.
The app currently runs on `k8s-w-1`; its database and read-only recovery
snapshot are tied to that worker.

See [backup and restore procedures](../../BACKUPS.md) and [cluster
recovery constraints](../../cluster/README.md).
