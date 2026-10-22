# SearXNG on Talos (Helm)

Migration of the `searxng` LXC Compose stack (SearXNG + Valkey + Newt) to the
Talos cluster, packaged as a local Helm chart. Everything is driven by one
playbook:

```sh
ansible-playbook playbooks/talos-cluster/searxng.yml -i inventory --vault-password-file .vault_pass
# -e searxng_action=verify    re-run in-cluster verification only
# -e searxng_action=cutover   -e searxng_public_url=https://...   move the Pangolin identity
# -e searxng_action=rollback  -e searxng_public_url=https://...   back to the LXC
```

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
  Gatus and the cutover gate to check health without opening search access.
- **One owner for the Newt identity.** `newt.enabled` defaults to `false`
  (staging). Only the playbook's `cutover` action enables it, after stopping
  the LXC stack and proving no containers remain; `rollback` disables it
  before restarting the LXC. Never flip it by hand outside those actions.
- **Backups**: the chart's `searxng-daily` Velero Schedule (Secrets excluded,
  `defaultVolumesToFsBackup: false`). Manifests-only is the *correct* outcome
  here -- the playbook asserts a completed backup with zero
  PodVolumeBackups, the inverse of the Homepage check.

## Before the first run (iteration checklist)

1. Add `searxng_secret_key` to Ansible Vault (`just edit-secrets`). Use the
   value from the LXC's `~/searxng/settings.yml` (`server.secret_key`) for
   continuity, or generate a fresh one; nothing user-facing depends on it.
2. Reconcile the `settings:` block in `chart/values.yaml` against that same
   live settings file (engine toggles, `instanceName`, `safeSearch`,
   `autocomplete`, `limiter`). The chart ships upstream-default readings
   plus the cluster Valkey URL and the `json` format (needed by the
   playbook's verification).
3. Check the Pangolin site's target for SearXNG (host and port); per the
   note above, `searxng:8080` and `localhost:8080` both work unchanged.
4. Sanity-check resource requests in `chart/values.yaml` against
   `docker stats` on the LXC; the shipped values are estimates.
5. On first rollout, watch the app logs for two watch-items: the image
   entrypoint vs. the read-only settings mount (chown), and whether the
   limiter interferes with the `/healthz` kubelet probes. If probes fail
   because of the limiter, fall back to `tcpSocket` probes like Valkey's.
6. Run `just lint` (with the vault password helper set) and
   `helm lint`/`helm template` on the chart before the first stage run.
