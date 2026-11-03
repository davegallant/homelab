# RFD Enrichment Kubernetes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Retire the `rfd-enrich` LXC and run its 15-minute deal enrichment CronJob with a dedicated LiteLLM proxy on Talos.

**Architecture:** Publish a minimal, immutable enricher container from the existing `rfd-fyi` source repository. Deploy LiteLLM with the official monolithic OCI Helm chart in `litellm`, and deploy the local CronJob chart in `rfd-enrich`; both namespaces get scoped Cilium policies and Vault-backed Secrets. Keep LiteLLM config-driven and database-free unless verification proves the active request path requires persistence.

**Tech Stack:** Kubernetes, Talos, Argo CD, Helm, LiteLLM official OCI chart, Node.js, GitHub Actions / GHCR, Ansible Vault, Cilium, Velero.

**Spec:** [kubernetes/RFD-ENRICH-DESIGN.md](../RFD-ENRICH-DESIGN.md)

## Global Constraints

- Work on local `main`; do not create another branch/worktree.
- Push only on Dave's explicit request; a push to homelab `main` under `kubernetes/**` does not apply live workloads automatically but daily sync/reconcile may affect applications.
- Keep secret values out of Git and command output; provision `OPENROUTER_API_KEY`, `REFRESH_SECRET`, and a generated `LITELLM_MASTER_KEY` from Ansible Vault.
- Keep LiteLLM internal behind a ClusterIP Service; expose no ingress, LAN, or tailnet endpoint.
- Pin the official Helm chart version, LiteLLM image version/digest, Node base image digest, and enricher image digest; never use moving tags.
- Run the enricher every 15 minutes with `concurrencyPolicy: Forbid`, bounded retries/deadline, non-root security context, dropped capabilities, read-only root, and no service-account token.
- Enforce Pod Security Restricted and Cilium policy in both namespaces; allow only the required job-to-proxy, RFD Pages, OpenRouter, and DNS traffic.
- Disable the LXC timer for cutover to prevent concurrent writes; require 48 hours of successful Kubernetes scheduled runs before LXC retirement.
- Do not add or run tests. Use manifest/chart rendering, repository lint, and the explicit live cutover checks below.

## Review Focus

- The active config uses OpenRouter; the documented device-login file may be stale. Prove a proxy start and request with only tracked config plus `OPENROUTER_API_KEY`; if device auth is required, stop and revise the approved storage design before proceeding.
- LiteLLM chart defaults include a standalone database and migration job. Verify both are disabled for the config-only deployment and that the final rendered Deployment, ConfigMap, Secret references, and Service match the selected pinned chart values.
- Argo's ordinary `homelab` project currently does not allow an upstream LiteLLM chart source or `CronJob`; update both the source allowlist and resource kind allowlist and render the Argo project/Application manifests.
- Cilium FQDN enforcement may not match the exact provider/API hostname path. Confirm OpenRouter, RFD Pages, and DNS flows with Hubble and retain only the required destinations.
- Image publishing and external-resource provisioning cross repository/service boundaries. Build and publish only after the source repo change is reviewed; do not push any repository or sync Applications without explicit authorization.

## File Structure

- `rfd-fyi/Dockerfile.enricher`: minimal Node runtime image containing only the enricher files needed at runtime.
- `rfd-fyi/.github/workflows/enricher-image.yml`: build and publish immutable image tags to GHCR on an explicit version tag.
- `kubernetes/apps/litellm/`: namespace, production values, and Cilium policy for upstream LiteLLM chart.
- `kubernetes/apps/rfd-enrich/chart/`: local Helm chart and values for the CronJob and its policy resources.
- `kubernetes/apps/rfd-enrich/`: namespace and Vault-to-Secret bridge values/template if required by the existing secret flow.
- `kubernetes/apps/argocd/applications/litellm.yaml` and `rfd-enrich.yaml`: manually synced applications.
- `kubernetes/apps/argocd/project.yaml`: permit upstream chart source, `CronJob`, and the two destination namespaces.
- `ansible/playbooks/talos-cluster/gitops-secrets.yml` and Vault group vars: provision namespace Pod Security labels and the OpenRouter / RFD ingestion Secrets.
- `kubernetes/RFD-ENRICH-DESIGN.md`: approved architecture and cutover gate.

## Implementation Tasks

### Task 1: Build an immutable enricher image

**Files:**
- Create in the existing `rfd-fyi` repository: `Dockerfile.enricher`
- Create in the existing `rfd-fyi` repository: `.github/workflows/enricher-image.yml`

**Interfaces:**
- Image entry point: `node /app/tools/enricher/enrich.mjs`.
- Required runtime inputs: `RFD_FYI_ORIGIN`, `ENRICH_MODEL`, `ENRICH_BASE_URL`, `ENRICH_STREAM`, `REFRESH_SECRET`; `ENRICH_API_KEY` remains optional.
- Published image tag is the immutable source commit SHA and the application values pin the resulting image digest.

- [x] Build from the public `rfd-fyi` source without installing runtime npm dependencies; copy `tools/enricher/enrich.mjs`, `lib.mjs`, and `providers.mjs` only.
- [x] Configure the workflow to publish only on an explicit `enricher-v*` tag, use GitHub's package write permission, and pin third-party actions to full commit SHAs.
- [x] Build the image locally; publish from the signed `enricher-v0.20.0` tag and pin the published SHA digest in production values.
- [ ] Do not publish the package or push a source tag until Dave explicitly authorizes the external write.

### Task 2: Add the official LiteLLM application

**Files:**
- Create: `kubernetes/apps/litellm/namespace.yaml`
- Create: `kubernetes/apps/litellm/values.production.yaml`
- Create: `kubernetes/apps/litellm/network-policy.yaml`
- Create: `kubernetes/apps/argocd/applications/litellm.yaml`
- Modify: `kubernetes/apps/argocd/project.yaml`
- Modify: `ansible/playbooks/talos-cluster/gitops-secrets.yml`
- Modify: encrypted Vault variables and `gitops-secrets` tasks to provision provider and master-key Secrets.

**Interfaces:**
- Upstream chart source: official OCI `ghcr.io/berriai/litellm-helm`, pinned exact chart version.
- Proxy config: existing model alias `gpt-6-luna` → `openrouter/openai/gpt-6-luna`; provider key and master key from namespace Secrets.
- Service: ClusterIP port 4000; job base URL `http://litellm.litellm.svc.cluster.local:4000/v1`.
- Database: `db.deployStandalone: false`, `migrationJob.enabled: false` only after config-only request validation confirms DB-less operation.

- [x] Fetch and inspect `helm show values` for the chosen exact chart version; confirm proxy config, Secrets, service, security context, and DB-less controls.
- [x] Add `litellm` namespace with Restricted Pod Security labels through the existing Ansible namespace workflow.
- [x] Add Argo Application and AppProject allowlists.
- [x] Configure the chart, provider/master-key Secrets, internal service, pinned non-root image, probes, and security settings; disable bundled Postgres and migrations for the current config-only use.
- [x] Add a Cilium default-deny policy for DNS and OpenRouter; permit only the enricher namespace/pod label on port 4000.
- [x] Mark the stateless LiteLLM Application `backup-policy: not-required`.
- [x] Migrate credentials to Vault and add provisioning tasks; values are never emitted in output.
- [ ] After authorized deployment, verify `/v1/models`, a representative model request, and device-login independence.

### Task 3: Add the enricher CronJob chart and application

**Files:**
- Create: `kubernetes/apps/rfd-enrich/namespace.yaml`
- Create: `kubernetes/apps/rfd-enrich/chart/Chart.yaml`
- Create: `kubernetes/apps/rfd-enrich/chart/values.yaml`
- Create: `kubernetes/apps/rfd-enrich/chart/templates/cronjob.yaml`
- Create: `kubernetes/apps/rfd-enrich/chart/templates/network-policy.yaml`
- Create: `kubernetes/apps/rfd-enrich/values.production.yaml`
- Create: `kubernetes/apps/argocd/applications/rfd-enrich.yaml`
- Create/update: Vault bridge values and `gitops-secrets` resources for `REFRESH_SECRET` and `ENRICH_API_KEY`.
- Modify: `kubernetes/apps/argocd/project.yaml`

**Interfaces:**
- Schedule: `*/15 * * * *`; `concurrencyPolicy: Forbid`.
- Container: immutable image from Task 1; command `/app/tools/enricher/enrich.mjs`.
- Enricher environment: RFD origin, model, LiteLLM service URL, stream setting, and Vault-backed `REFRESH_SECRET` and `ENRICH_API_KEY`; no local PVC.
- Argo project permits `batch/CronJob` and the `rfd-enrich` destination.

- [x] Add namespace manifest with Restricted enforcement and register it in `gitops-secrets`.
- [x] Add CronJob template with bounded retries/deadline, non-root UID/GID, RuntimeDefault seccomp, read-only root, dropped capabilities, resource bounds, and no service account token.
- [x] Add Cilium default-deny policies allowing DNS, HTTPS to RFD Pages, and TCP 4000 to LiteLLM with matching ingress labels.
- [x] Add the `rfd-enrich` Argo Application with `backup-policy: not-required`.
- [x] Render the local chart and inspect immutable image reference, env/Secret references, Cilium labels/ports, schedule, and security context.

### Task 4: Provision, cut over, and prove retirement readiness

**Files:**
- Modify as required: `ansible/playbooks/talos-cluster/gitops-secrets.yml` and Vault variable templates.
- No live resource files are generated into the repository.

**Interfaces:**
- LiteLLM Secrets contain the provider key and master key; the job gets the master key only as its LiteLLM client key.
- Enricher secret contains the existing RFD `REFRESH_SECRET`.
- LXC remains recoverable until 48 hours of successful Kubernetes scheduled runs are observed.

- [ ] Verify intended Kubernetes API/context and all expected node names before any cluster mutation.
- [ ] Provision namespaces, Pod Security labels, and external Secrets using the protected `gitops-secrets` playbook. Never print secret values.
- [ ] Review Argo diffs and sync LiteLLM first; verify Ready/healthy state, `/v1/models`, one model request, and Hubble allow/deny evidence before syncing the CronJob.
- [ ] Disable `rfd-enrich.timer` on the LXC at cutover to prevent concurrent writes, then start one Kubernetes Job manually and verify it fetched input, called LiteLLM, posted accepted tags, and exited successfully.
- [ ] Enable/retain the 15-minute CronJob and observe 48 hours of successful scheduled runs. If a gate fails, retain the LXC and stop the retirement path.
- [ ] After Dave explicitly authorizes shutdown/retirement, stop and disable the LXC services, verify Kubernetes remains healthy, and only then remove LXC inventory/provisioning references in a separate reviewed change.

## Validation Commands

- `helm template` the LiteLLM chart at its pinned version with the tracked production values.
- `helm template` the local `rfd-enrich` chart.
- Run `just lint` from the repo root with the protected Vault password file configured for Talos syntax checking.
- Inspect rendered Argo Projects/Applications, namespace Pod Security labels, CronJob and Cilium policies.
- After authorized sync, verify live readiness, model response, one manual CronJob result, required Hubble traffic, and the full 48-hour scheduled run window.
