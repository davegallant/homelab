# Umami on Talos

Argo CD manages Umami from `values.production.yaml`; its Application is
`../argocd/applications/umami.yaml`. Follow the [release management
guide](../argocd/MANAGEMENT.md) for updates and recovery.

Umami and PostgreSQL run in one pod. Pangolin provides public access through
the Newt sidecar. PostgreSQL state uses a local-path PVC; the
`umami-daily` Velero schedule backs it up with a `pg_dump` hook. Secrets
are provisioned from Vault by `playbooks/talos-cluster/umami-secret.yml`.

See [backup and restore procedures](../../BACKUPS.md) for recovery.
