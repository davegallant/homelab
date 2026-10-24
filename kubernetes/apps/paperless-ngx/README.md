# Paperless-ngx on Talos

Argo CD manages Paperless-ngx from `values.production.yaml`; its Application
is `../argocd/applications/paperless-ngx.yaml`. Follow the [release
management guide](../argocd/MANAGEMENT.md) for updates and recovery.

Paperless and Redis run in one pod. Pangolin provides public access through
the Newt sidecar. SQLite and document state use four local-path PVCs:
`data`, `media`, `consume`, and `export`. The Velero schedule
`paperless-ngx-daily` backs up all four; a pre-backup hook creates a
consistent SQLite copy in the data volume. Redis state is disposable.

Secrets are provisioned from Vault by
`playbooks/talos-cluster/paperless-secret.yml`. See [backup and restore
procedures](../../BACKUPS.md) for recovery.
