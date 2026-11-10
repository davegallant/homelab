# Configuration audit implementation

Execute on local main, in separate commits by concern. Do not push or deploy.

- Preserve Compose rollback images; move image cleanup to opt-in maintenance.
- Add a rendered Grafana alert for watchdog last-success age, absence and suspension.
- Derive an inventory from tracked Applications and Ansible imports; validate a
  small lifecycle catalog instead of duplicating deployment configuration.
- Add a read-only live retirement report for retained PVCs and missing owners.
- Remove obsolete runner pilot prose while retaining current trust constraints.
- Document isolated restore acceptance criteria for SQL, SQLite and mixed NAS data.
- Define exposure, monitoring, retirement and incident-artifact retention patterns.

Use existing tools, test new Python behavior with fixtures before implementation,
run repository checks and review each diff before committing. No service is removed
without live ownership and usage evidence. Historical material remains available
until its recovery value has been assessed. Live restore drills require isolated
resources and explicit handling of production identities.

## Execution record (2026-11-10)

Implemented: deployment/image-cleanup separation; removal of obsolete Miniflux
configuration following Dave's confirmation; Grafana watchdog freshness alert;
derived service inventory and read-only retirement report with fixture tests;
runner comment cleanup; restore matrix and service lifecycle guidance.

Validation: `just lint` passed, including 35 Python tests, rendered Pod Security,
backup coverage, Ansible lint, shellcheck and Renovate validation. Grafana chart
render and modified alert YAML validation passed after the final query change.

Read-only live observations against `homelab`, API `192.168.1.210:6443`:
all three expected nodes Ready; 15 unmounted PVC candidates; no missing Argo
tracking owners among the resource kinds queried. Receipts are ignored and zero
receipt files are tracked. The scheduled backup watchdog last succeeded on
2026-11-08; its November 10 Job failed with BackoffLimitExceeded. Two later
manual audit Jobs completed. The failed Job's pod is absent, so its logs were
not recoverable through `kubectl logs`. Do not infer scheduled recovery from
those manual completions. A kube-state-metrics service proxy request timed out;
metric presence and alert delivery remain deployment acceptance checks.

Remaining operational work: approve a push before remote Argo syncs; verify the
new alert's metric and notification path; establish a fully off-cluster heartbeat
with an independently reachable notification destination; run the isolated restore
drills; investigate the next scheduled watchdog run; review each retained PVC
before deletion. No live service, PVC, credentials or backup was deleted. No
restore drill or deployment was performed. Retiring Beszel, Headlamp or
k8s-readonly still needs actual usage evidence; these are review candidates,
not approved removals inferred from functional overlap.
