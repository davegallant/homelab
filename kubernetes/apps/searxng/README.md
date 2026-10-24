# SearXNG on Talos (Argo CD)

## Current operations

Argo CD manages the production resources. Follow [release management](../argocd/MANAGEMENT.md)
for updates, external Secrets, and recovery. Use the tracked production values
and Application definition for desired state. Do not run Helm mutations against
resources owned by Argo CD.

## Layout

- `chart/` -- the Helm chart: app Deployment (optional Newt sidecar), Valkey
  Deployment + Service, app Service, settings and Newt Secrets, and the
  Velero Schedule (into the `velero` namespace). Fixed resource names
  (`searxng`, `valkey`, `searxng-daily`) on purpose -- single-instance
  internal app, no fullname templating.
- `chart/values.yaml` -- committed defaults; images are the exact
  version+digest pins from the LXC Compose file. Secret-bearing values ship
  empty and the chart refuses to render without them (`required`).
- `values.secrets.yaml.j2` -- Ansible template that injects the Vault values
  (`searxng_secret_key`, `searxng_newt_id`, `searxng_newt_secret`,
  `pangolin_endpoint`) as a Helm values file, rendered by the playbook into a
  protected temp dir and deleted after the run. Never commit a rendered copy.

## Design

- **No static PVs, no node pinning.** SearXNG's only state is its settings
  (a chart-rendered Secret, key from Vault) and the Valkey cache/limiter
  data (an `emptyDir`, reset on pod restart -- acceptable for a cache). The
  workload schedules on either worker. The LXC's Valkey volume is
  deliberately not migrated.
- **Exposure is Pangolin/Newt, not the tailnet.** The Compose stack publishes
  no ports; traffic arrives through the Newt tunnel. In the pod, Newt shares
  the app container's network namespace, so the existing Pangolin site keeps
  working: a target of `searxng:8080` resolves to the Service and
  `localhost:8080` reaches the app directly.
- **Pangolin SSO stays enabled for the search UI.** Its `/healthz` path has a
  `Bypass Auth` rule followed by a catch-all `Pass to Auth` rule, allowing
  Gatus to check health without opening search access.
- **Newt identity:** production values enable the existing Pangolin
  identity in the pod. Keep its Secret Ansible-managed and out of Git.
- **Backups**: the chart's `searxng-daily` Velero Schedule (Secrets excluded,
  `defaultVolumesToFsBackup: false`). Manifests-only is the *correct* outcome
  here -- the playbook asserts a completed backup with zero
  PodVolumeBackups, the inverse of the Homepage check.
