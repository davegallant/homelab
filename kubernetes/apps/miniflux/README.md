# Miniflux on Talos

Argo CD manages Miniflux from `values.production.yaml`; its Application is
`../argocd/applications/miniflux.yaml`. Follow the [release management
guide](../argocd/MANAGEMENT.md) for updates and recovery.

The app and PostgreSQL run in the `miniflux` namespace. PostgreSQL uses a static local PV on `k8s-w-1`; its data is not on NFS. Credentials come from Vault and Secrets are excluded from backups.

The `miniflux-daily` Velero schedule backs up the database volume and runs a
`pg_dump` hook before each backup. Restore the volume first; use the dump if
the data directory cannot be recovered. See [backup and restore
procedures](../../BACKUPS.md) and [cluster recovery
constraints](../../cluster/README.md).
