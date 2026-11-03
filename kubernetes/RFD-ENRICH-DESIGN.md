# RFD Enrichment on Kubernetes

## Intent

Retire the `rfd-enrich` LXC and run the existing RedFlagDeals enrichment process
on Talos. The process tags untagged deals with an LLM and posts tags to the
deployed RFD Pages app. The LXC currently schedules it every 15 minutes, and
LiteLLM runs locally beside it.

## Goals

- Run enrichment as a Kubernetes `CronJob` every 15 minutes.
- Run LiteLLM continuously in its own `litellm` namespace and the enricher in a
  separate `rfd-enrich` namespace.
- Keep LiteLLM configuration and credentials in Kubernetes-managed resources;
  persist auth state only if the current OpenRouter configuration requires it.
- Keep `OPENROUTER_API_KEY`, `REFRESH_SECRET`, and the LiteLLM master key in
  Ansible Vault and provision scoped Kubernetes Secrets through the existing
  `gitops-secrets` flow.
- Manage both workloads through Argo CD and retire the LXC only after a
  successful Kubernetes run and an agreed observation period.

## Findings and constraints

- `rfd-enrich.timer` runs every 15 minutes with randomized delay. Its
  `Type=oneshot` service runs `/opt/rfd-fyi/tools/enricher/enrich.mjs` under
  Node and exits. The script fetches topics and enrichment instructions from
  `https://rfd.davegallant.ca`, classifies untagged topics, and posts batches
  back to the app. It has no local application data.
- LiteLLM runs at `127.0.0.1:4000` on the LXC. Its tracked runtime config
  routes `gpt-6-luna` through OpenRouter, and the service receives
  `OPENROUTER_API_KEY`. The host README also describes a ChatGPT device-login
  file at `/var/lib/rfd-enrich/.config/litellm/auth.json`; that may be stale
  state and must not be assumed necessary. Proxy config and provider env are
  under `/etc/rfd-enrich`.
- Current runs fail: the proxy restart loop reports
  `ModuleNotFoundError: No module named 'litellm'`, and the enricher cannot
  reach the proxy.
- This repo uses Argo CD Applications with local Helm charts, manually approved
  syncs, per-application network policies, and Vault-provisioned external
  Secrets. Namespace workloads normally enforce Pod Security Restricted.
- The cluster storage guide requires an explicit local storage and backup
  decision for every new persistent volume. LiteLLM auth state is not covered
  by Velero by default unless its volume is supported and verified.

## Approaches

1. **Official LiteLLM chart plus a small local CronJob chart — selected.** Use
   the upstream monolithic LiteLLM Helm chart in `litellm`, after verifying its
   pinned chart version supports the existing proxy config and required mounts.
   Define the `rfd-enrich` CronJob, namespace policy, and app resources
   in a small repository-owned chart. This minimizes local chart maintenance
   while retaining control of the scheduled workload.
2. **Repository-owned charts for both workloads.** This offers direct control
   over every template and mount, but adds ongoing LiteLLM chart maintenance.
3. **A single local chart for both workloads.** This makes the deployment
   self-contained but couples an independently useful service with one batch
   client and still requires owning the LiteLLM templates.

The official LiteLLM chart is pinned to 1.106.6 and uses its monolithic proxy
deployment; no componentized gateway/backend/UI topology is needed.

## Proposed design

- Add two Argo CD Applications: `litellm` for the upstream Helm chart and
  `rfd-enrich` for a small local Helm chart. Keep each in its own namespace and
  ordinary `homelab` Argo project. Record the appropriate backup policy in
  each Application.
- Run the LiteLLM proxy as one Deployment replica behind a ClusterIP Service.
  Do not expose it through an ingress or gateway. Pin the chart and image
  versions; do not use a moving tag. Keep the proxy config-driven and DB-less
  if the live request path confirms no UI, virtual keys, or spend tracking are
  needed; disable the chart's bundled Postgres and migrations in that case.
- Mount LiteLLM config from a ConfigMap and secrets from Kubernetes Secrets
  provisioned from Ansible Vault. Set `OPENROUTER_API_KEY` and
  `LITELLM_MASTER_KEY` in the LiteLLM namespace; copy only the master key as
  `ENRICH_API_KEY` into the job namespace, alongside `REFRESH_SECRET`. Do not
  persist `/home` or `/var/lib` by default. If the running config or successful
  request proves device-login files are required, stop and revise the design
  to add a supported local PVC and verified backup and restore path before
  cutover.
- Run the enricher as a non-root `CronJob` on `*/15 * * * *` with
  `concurrencyPolicy: Forbid`, bounded retries and deadline, small resource
  requests, read-only root filesystem, dropped capabilities, and no service
  account token. Add a Dockerfile and image-publish workflow to the existing
  `rfd-fyi` source repo, then reference a published immutable GHCR digest; its
  runtime script has no installed Node dependencies.
- Set the job's LiteLLM base URL to the cross-namespace service DNS name
  `http://<service>.litellm.svc.cluster.local:4000/v1`. Inject `REFRESH_SECRET`
  and any proxy API key from separately scoped Kubernetes Secrets.
- Add narrowly scoped Cilium policies: LiteLLM accepts ingress only from the
  `rfd-enrich` workload on the proxy port; the job may reach that service and
  the RFD Pages HTTPS endpoint. LiteLLM egress is limited to OpenRouter and
  cluster DNS. Verify exact destinations and Cilium behavior before relying on
  the policy.
- Keep the current LXC available during rollout, but do not allow both timers
  to write concurrently. Disable its timer for the Kubernetes cutover, run a
  Kubernetes job, and verify successful classification/posting in job logs and
  the deployed app. Require 48 hours of successful scheduled Kubernetes runs
  before retiring the LXC.

## Non-goals

- Changing the enrichment prompt, classification algorithm, frequency, model,
  or RFD Pages API.
- Exposing LiteLLM to LAN, tailnet, or public clients.
- Migrating application data; there is no local enricher data to migrate.
- Applying Kubernetes resources or retiring the LXC as part of this design
  approval.

## Remaining implementation gates

- Publish the enricher image to GHCR after Dave authorizes the external write,
  then replace the documented digest placeholder with the registry digest.
- Render and inspect both charts. The official chart values confirm external
  proxy config and Secrets, DB-less settings, internal service, and extra
  resources are supported. A successful OpenRouter request and Cilium traffic
  checks require an authorized cluster deployment.
- The LXC currently reports a LiteLLM import failure; device-login state is
  mentioned in its README but the active config uses OpenRouter. Confirm
  stateless operation against the cluster proxy before disabling the LXC timer.
- The 48-hour successful-run observation remains the retirement gate.
