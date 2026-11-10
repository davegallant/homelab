# Service lifecycle and preferred patterns

## Inventory

Run `just service-inventory` for a derived deployment catalog: active Argo
Applications and imports in the all-host Ansible playbook. Source files remain
authoritative; an application directory alone does not establish deployment.
Manual infrastructure playbooks are not daily service targets. This inventory
is desired state, not proof a service is running or used.

Keep exposure, health endpoint and storage protection beside the owning
application. Before onboarding, follow the Argo checklist and run `just lint`:
it checks backup declarations, rendered PVC coverage and Pod Security. Do not
create a second hand-maintained list of image versions or namespaces.

## Preferred patterns

- Tailnet HTTP applications: prefer the shared tailnet Gateway. Keep dedicated
  Tailscale/Caddy sidecars when identity, protocol or routing needs justify them.
- Public applications: use the existing Pangolin/Newt pattern and explicit
  authentication. Do not publish private admin interfaces for convenience.
- Monitoring: Gatus observes availability from outside Kubernetes; Grafana and
  VictoriaMetrics cover workload and cluster metrics. Beszel covers the remaining
  host estate. Overlap is intentional only where it answers different questions.
- Scheduled application jobs: prefer existing Argo Workflows. Use the privileged
  Docker runner only for trusted workflows that actually require Docker execution.
- Stateful storage: follow `kubernetes/STORAGE.md`; local SQLite, explicit backup
  selection, resource requests and disabled API tokens unless required.
- Health: prefer application health endpoints over login pages. For complex
  applications, include database/API functionality and required WebSockets.

## Retirement

Run `just retirement-report` after checking the current kubeconfig context. It
queries only read-only APIs, reports the API address and never reads Secrets.
Unmounted claims and resources tracked to absent Applications are candidates,
not deletion authorization. The report is intentionally incomplete: it does not
render scaled-down controllers, discover every custom resource, or establish usage.

For each candidate, record owner, last observed use, dependencies, protection,
restore proof and a retirement date. Check DNS, Gateway routes, Headscale policy,
Gatus, Homepage, notification tokens and scheduled jobs. Stop producers first;
retain protected rollback data for a stated period. Remove resource configuration
and live resources separately, with a reviewed per-resource deletion list.
Never use bulk pruning to infer what is safe to delete.

Miniflux is removed. Beszel, Headlamp and k8s-readonly remain until usage and
access requirements establish that one can be retired. Do not equate similar
names or UI functions with redundant operational needs.

## Incident evidence

`kubernetes/receipts/` is already ignored by Git. Its local size does not imply
that all captures are tracked. Preserve a concise incident summary: cause,
resolution, recovery checks and references to protected evidence. Keep raw captures
outside normal configuration with a default 90-day review, longer when recovery
or unresolved investigations require it. Review credentials and sensitive metadata
before archiving or sharing. Never rewrite repository history merely to move logs.
