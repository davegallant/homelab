# Forgejo Docker runner (K8s)

Status: DRAFT by Tux, 2026-10-25. NOT synced, NOT committed (Codex to verify
git chart version + keys + registration, then commit/push + sync — see
`/Users/dave/codex-prompt-k8s-docker-runner-resume.md`, updated 2026-10-25
for official git repo chart, Option B).

## Chart source (Dave-approved, Option B, 2026-10-25)

OFFICIAL GIT REPO: https://code.forgejo.org/forgejo-helm/forgejo-runner
NOT OCI (oci://code.forgejo.org/forgejo-helm/forgejo-runner 404s —
package does not exist, Codex stopped correctly at Step 1, no mutation).
NOT wrenix OCI (third-party, final-release hint, parked).
VSHN ADR 0054 links this repo as the 'official Forgejo runner Helm
chart', structurally identical to the former wrenix upstream chart.
Codex must clone the repo, read Chart.yaml (name, version, appVersion)
and values.yaml, list tags, and set the Argo source to the verified
tag/branch + chart path — do NOT guess a version, do NOT use OCI.

## Why this exists

Public Forgejo moved to K8s 2026-10-25 (Forgejo 1/1 w-1, Newt 1/1 w-2).
Dave then stopped the whole Forgejo LXC himself, so docker-runner-1/2 +
DinD in that LXC are stopped. Docker workflows (gaswatch hourly,
rfd-notify-cron 5-min, both `runs-on: docker`) now queue with no docker
runner. Host runner host-runner-1 on CT107 is separate and unaffected.

There was NO live forgejo-runner Argo app and NO forgejo-runner files in
the Mac checkout on 2026-10-25 (searched 723 files, 0 matches). This app
is (re)created from scratch here, it is not a sync of a staged app.

## Design (Dave-approved, Option B, internal)

- Official Forgejo runner Helm chart, Docker executor, DinD privileged.
- Labels: `docker` ONLY. Do NOT add host/tailscale labels.
- Instance URL: INTERNAL `http://forgejo.forgejo.svc.cluster.local:3000`
  (Service `forgejo` in namespace `forgejo`, ClusterIP 10.108.114.70,
  port 3000, live 2026-10-25). NOT public URL.
  - Why internal: no Pangolin/Newt dependency, works if Newt/public down,
    lower latency, Docker jobs move off w-1/LXC to w-2 (runner has no PVC).
  - Why public was used before: LXC runners used public, and job
    containers on DinD bridge can reach public via internet. Internal
    needs the two traps below handled, otherwise it fails silently.
- Namespace: `forgejo-runner`, privileged (DinD requires it).
- Argo project: `homelab-platform`, NOT `homelab`.
  - `homelab` project does not list `code.forgejo.org/forgejo-helm` as a
    source, does not list `forgejo-runner` as a destination, and has
    `clusterResourceWhitelist: []` (Namespace is cluster-scoped).
  - `homelab-platform` already lists forgejo-helm as a source and allows
    Namespace / ClusterRole / CiliumNetworkPolicy, like the server app.
  - Destination `forgejo-runner` must be added to platform-project.yaml
    (Codex step, separate commit if needed, report it).
  - Namespace itself is hand-applied (this file), like k8s-readonly
    namespace + RBAC were hand-applied — Argo syncs the workload only,
    Codex must verify live whether the chart needs cluster-scoped
    objects beyond Namespace and report them.
- DinD storage: emptyDir for pilot. Image cache lost on pod restart,
  jobs re-pull. Acceptable for small gaswatch/rfd-notify jobs.

## Trap 1: Cilium ingress to Forgejo (MUST fix, or runner cannot poll)

Forgejo policy `forgejo-default-deny` (in `apps/forgejo/values.production.yaml`)
ingress currently allows ONLY host + same-namespace (forgejo) pods.
A runner in namespace `forgejo-runner` is neither, so its traffic to
Forgejo pods will be DENIED, even though runner namespace itself has
no policy (egress allowed by default).

Fix, in forgejo values, separate commit, sync Forgejo app:
add an ingress entry to `forgejo-default-deny`:

```yaml
- fromEndpoints:
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: forgejo-runner
  toPorts:
    - ports:
        - port: "3000"
          protocol: TCP
```

Verify live with diagnostic pod / Hubble AFTER the rule: runner-namespace
pod -> Forgejo:3000 must be ALLOWED. Do NOT sync the runner until this
is proven, or the runner will fail with a Cilium denial that looks like
a Forgejo outage. Same class of bug as the attempt-2 503.

## Trap 2: Job-container checkout (runner online does NOT prove jobs work)

DinD job containers run on their OWN Docker bridge network, NOT the K8s
pod network, so they CANNOT resolve K8s DNS names and CANNOT reach
ClusterIP by name — unless given a host mapping. With a public instance
URL this trap does not exist (job containers reach public via internet).

Fix, in runner config (values.production.yaml, keys verified against
real chart): job-container options must include:

```
--add-host=forgejo.forgejo.svc.cluster.local:10.108.114.70
--add-host=forgejo:10.108.114.70
```

ClusterIP 10.108.114.70 is stable as long as Service `forgejo` exists
(re-verify live before sync — if it changed, update add-host values).

Gate: Codex MUST run a REAL docker workflow (scratch, or next
rfd-notify-cron 5-min run) and verify CHECKOUT succeeds, not just runner
online. If checkout fails with add-host, fallback is
`container.network: host` (job containers share pod network, can resolve
K8s DNS, lower isolation — trusted workflows only: gaswatch +
rfd-notify, Dave's own code, no untrusted PRs). Fallback needs Dave
approval in that run, do NOT silently switch, report failure verbatim.

## Registration

From Vault, NEVER Git, NEVER printed. Official chart pattern:
`runner.config.existingSecret` points at a pre-built `.runner` file,
skipping the chart's own registration job.

If a registration token must be created in Forgejo admin, Codex must
STOP and report the exact Vault/secret step for Dave to provide it.
Do NOT reuse the host-runner token, do NOT rotate any token on your own,
do NOT put a token value in Git.

## Files (Tux-created, Codex to verify + complete)

- `kubernetes/apps/argocd/applications/forgejo-runner.yaml` — Application,
  project homelab-platform, chart forgejo-runner, targetRevision
  TODO_RUNNER_CHART_VERSION (Codex to replace with verified version).
- `kubernetes/apps/forgejo-runner/namespace.yaml` — Namespace, privileged.
- `kubernetes/apps/forgejo-runner/values.production.yaml` — values draft,
  keys to be verified against `helm show values` for the verified chart
  version, TODO_RUNNER_SECRET_NAME to be set from Vault flow.
- `kubernetes/apps/forgejo-runner/README.md` — this file.
- `kubernetes/apps/argocd/platform-project.yaml` — destination
  forgejo-runner to be added by Codex (report it).
- `kubernetes/apps/forgejo/values.production.yaml` — Cilium ingress
  entry for forgejo-runner namespace to be added by Codex (separate
  commit, sync Forgejo app, verify with Hubble).

## What this does NOT do

- Does NOT restart Forgejo LXC, does NOT start docker-runner-1/2.
- Does NOT use public Forgejo URL for the runner.
- Does NOT edit production workflows, homelab CI labels, Headscale ACL,
  Pangolin, or any other app (except the Forgejo Cilium ingress entry
  above, which is required for internal to work).
- Does NOT delete LXC data, old PVCs, or rollback mounts.
