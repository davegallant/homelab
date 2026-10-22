# SearXNG on Talos

Migration of the `searxng` LXC Compose stack (SearXNG + Valkey + Newt) to the
Talos cluster. Written 2026-10-22; deploy and iterate via the talos-cluster
playbooks (`apply-searxng.yml`, `verify-searxng.yml`, `cutover-searxng.yml`,
`rollback-searxng.yml`).

## Design

- **Namespace `searxng`, no static PVs, no node pinning.** SearXNG's only state
  is its settings file and the Valkey cache/limiter data. Settings live in the
  `searxng-settings` Secret (rendered from `settings.yaml.j2`, secret key from
  Ansible Vault); Valkey runs on an `emptyDir`, so its data resets when the pod
  restarts -- acceptable for a cache/limiter store, and the reason this
  workload can schedule on either worker. The LXC's Valkey volume is
  deliberately not migrated.
- **Exposure is Pangolin/Newt, not the tailnet.** The Compose stack publishes
  no ports; traffic arrives through the Newt tunnel. The cluster pod carries
  Newt as a sidecar sharing the pod network namespace, so the existing
  Pangolin site keeps working: a target of `searxng:8080` resolves to the
  Service, and `localhost:8080` reaches the app container directly.
- **One owner for the Newt identity.** `searxng_newt_enabled` in `vars.yaml`
  defaults to `false` (staging: app + Valkey only, verified in-cluster). Only
  `cutover-searxng.yml` enables Newt, and only after it has stopped the LXC
  stack; `rollback-searxng.yml` reverses the order.
- **Backups**: Velero schedule `searxng-daily`
  (`apps/velero/schedule-searxng.yaml`), applied and exercised by
  `apply-searxng.yml`. Manifests-only by design: Secrets are excluded
  (re-creatable from Vault via the apply playbook) and
  `defaultVolumesToFsBackup: false` -- there are no persistent volumes to
  capture. A completed backup with zero PodVolumeBackups is the *expected*
  outcome here, unlike Homepage.
- Images are the exact version+digest pins from the LXC Compose file.

## Before the first apply (iteration checklist)

1. Add `searxng_secret_key` to Ansible Vault (`just edit-secrets`). Use the
   value from the LXC's `~/searxng/settings.yml` (`server.secret_key`) to keep
   continuity, or generate a fresh one -- nothing user-facing depends on it.
2. Reconcile `settings.yaml.j2` against that same live settings file (engine
   toggles, `instance_name`, `safe_search`, `autocomplete`, limiter on/off).
   The template ships upstream-default readings plus the cluster Valkey URL
   and the `json` format (needed by `verify-searxng.yml`).
3. Check the Pangolin site's target for SearXNG (host and port) and confirm it
   matches the note under Design; adjust the target at cutover if it is
   neither `searxng:8080` nor `localhost:8080`.
4. Sanity-check the resource requests in `deployment.yaml.j2` / `valkey.yaml`
   against `docker stats` on the LXC; the shipped values are estimates.
5. On first rollout, watch the app logs for two known watch-items: the image
   entrypoint vs. the read-only settings mount (chown), and whether the
   limiter interferes with the `/healthz` kubelet probes. If probes fail
   because of the limiter, fall back to `tcpSocket` probes like Valkey's.
