# Headplane

Headplane is the admin UI for the existing Headscale server on the VPS. The
Kubernetes workload reaches Headscale through its HTTPS URL; it does not join
the tailnet itself. The UI is served at
`https://headplane.tail.davegallant.ca/admin` through the tailnet-only Cilium
Gateway. Headscale's VPS Traefik adds CORS headers limited to this UI origin.

Headplane is configured with the remote Headscale URL, but without access to
Headscale's config file or Docker socket. The UI therefore manages API-backed
Headscale resources while configuration-file and Docker integration features
remain unavailable. Users log in with a Headscale API key created on the VPS.
The cookie signing secret is stored in Ansible Vault and provisioned as the
external `headplane-external` Secret by `gitops-secrets.yml`.

Headplane's internal database and cache live in the `headplane-data` PVC. The
PVC uses the `local-path` StorageClass with `volumeType: local`; Velero's
`headplane-daily` Schedule backs it up. The pod is pinned to `k8s-w-1`, where
the volume binds; restore through Velero after ensuring that worker has the
required local storage. Secrets are excluded from Velero and recreated from
Vault.

## Operations

- Edit the chart and production values, then approve a manual Argo CD sync.
- Sync the `headplane` workload before the `tailnet-gateway` route update.
- Run `just run talos-cluster/gitops-secrets` after the namespace exists to
  provision the cookie secret.
- Verify the route at `/admin`, create a Headscale API key on the VPS, and
  enter it at the login page.
- Verify the Velero Schedule is enabled and the first backup contains a
  completed PodVolumeBackup with nonzero bytes before considering data
  protection proven.
- Roll back by reverting the tracked chart/config and approving another
  Argo CD sync. Do not delete the PVC during rollback.
