# Kubernetes application managed by Argo CD

## Read first

Read `kubernetes/README.md`, `kubernetes/cluster/README.md`,
`kubernetes/apps/argocd/MANAGEMENT.md`, `kubernetes/SECURITY.md`, and
`kubernetes/BACKUPS.md`. Use a comparable application's current manifests
as a reference; migration-specific rollback volumes are not new-app defaults.

## Scaffold

1. Create `kubernetes/apps/<service>/` with `values.production.yaml` and a
   README describing exposure, dependencies, Secrets, storage, backups,
   validation, deployment, and recovery. Prefer the existing pinned
   app-template pattern for a simple workload; use a local `chart/` when
   the topology warrants it. Pin chart versions and container images to
   a version and SHA digest, including sidecars.
2. Add `kubernetes/apps/argocd/applications/<service>.yaml`. Match an
   existing Application's source/value layout, destination namespace,
   `homelab` project, and sync options. Keep manual sync, with automated
   sync, pruning, and deletion finalizers absent. Add the namespace and
   any required source or resource permissions to
   `kubernetes/apps/argocd/project.yaml` with the narrowest scope.
3. Define namespace and storage ownership explicitly. Keep Pod Security
   baseline; exceptions require separate review. Set resource requests,
   limits, and useful startup/readiness/liveness probes. Check worker
   allocatable resources and scheduled requests before deployment. Choose
   local or NAS storage deliberately and document node affinity, capacity,
   backup coverage, and restore constraints for persistent data.
4. Choose exposure: userspace Tailscale or Pangolin/Newt according to the
   service's intended audience. Define Services and narrowly scoped Cilium
   policy for DNS, ingress, dependencies, and required egress. Userspace
   Tailscale does not give the application automatic outbound tailnet
   routing or MagicDNS; account for application API and widget traffic.
5. Keep Secret values in Ansible Vault and reference external Secrets in
   production values. Extend the appropriate protected secret provisioning
   flow under `ansible/playbooks/talos-cluster/`, following
   `gitops-secrets.yml` or an existing app-specific secret playbook.
   Preserve the ownership split between Argo CD workloads and external
   Ansible resources; keep rendered secrets outside Git and command output.
6. For persistent data, complete the daily coverage and volume gates in
   `kubernetes/STORAGE.md`, including the tracked schedule and live Enabled
   check. Configure backup schedules and volume selection,
   with database-consistent dumps/hooks where needed. Exclude Secrets and
   live Tailscale identities as required by the backup runbook. Document
   restore prerequisites. Add the app to `kubernetes/README.md`, then
   return to the shared Homepage and Gatus steps in `SKILL.md`.

An Argo CD application needs no LXC inventory entry or all-host playbook
import. Talos provisioning playbooks remain outside that CI flow.

## Validate and deploy

Render the pinned chart with production values and inspect the manifests
for valid resource references, image digests, probes, policy, storage, and
external Secret names. Syntax-check any added Ansible playbooks with the
Vault password helper. Complete the shared validation before reporting
readiness. Rendering alone does not establish live application health.

When deployment is authorized, follow release management: publish the
reviewed sources only on an explicit push request, provision namespace,
storage and external resources in dependency order, apply project changes
and the Application definition, review the Argo CD diff, then obtain the
required sync approval. Sync without prune or force. Use Argo CD for
workload changes and rollback; Helm is for rendering, not live upgrades.

Verify Synced/Healthy, readiness, actual application API calls through the
intended URL, and completed backups for persistent workloads. Report any
live checks that remain pending when deployment is outside the request.
