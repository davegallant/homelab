# Release management

Application definitions cover service workloads and cluster infrastructure,
including Argo CD itself. See the [workload index](../../README.md) and the
tracked [Application definitions](applications/) for the current inventory.
Charts remain Helm templates, while Argo CD owns their deployed resources. Historical Helm
release records are retained for reference; `helm list` is not an ownership
inventory. Do not run `helm upgrade`, `helm rollback`, or `helm uninstall`
against these releases.

Application definitions live in `applications/`. The `argocd` Application
renders this directory as a Git source, so syncing `argocd` reconciles all
Application definitions from `main`. The `homelab` project owns ordinary
service applications. VictoriaMetrics and Velero backup Schedules use
separate projects because their destination namespaces are privileged; each
project permits only the resource kinds those Applications manage. The
`velero-schedules` Application owns the backup Schedules for ordinary services,
so service Applications do not need access to the privileged `velero` namespace.
Each ordinary Application declares `homelab.davegallant.ca/backup-policy` as
`scheduled` or `not-required`; `just lint` checks that decision against the
central Schedule inventory. When adding a service, make the decision in its
Application definition and add its Schedule to `kubernetes/apps/velero-schedules/`
when required.
`homelab-platform` permits the pinned upstream repositories and the cluster
resource kinds required by infrastructure charts. `tailnet-gateway` uses its
own project, limited to Gateway, HTTPRoute, and Cilium network policy resources
in the namespaces where its routes and policies live, plus the four cluster
resource kinds it renders. All Applications require manual sync except the
qBittorrent egress guardrail; none has pruning or a deletion finalizer.
Upstream charts use multiple sources: a pinned chart plus values from GitHub
`main`. Custom charts read their sibling `values.production.yaml`.

Edit values, chart templates, and Application definitions in Git, push, review
the Argo CD diff, then approve Sync without prune or force. Syncing `argocd`
updates Application definitions; sync each changed workload separately.
Storage objects outside the charts are
not adopted or recreated. Namespace Pod Security labels are preserved.
Use server-side apply for the platform charts, including their large CRDs.

## Adding a new application

This checklist exists because the Headlamp onboarding (2026-11-04) tripped
on steps that were only documented in scattered file headers, not in one
place. Work through it in order; each step's failure mode is listed so a
failed sync is diagnosed instead of retried blindly.

1. Application definition. Add `kubernetes/apps/argocd/applications/<service>.yaml`
   with the `homelab` project (or the narrowest project that fits), the
   destination namespace, manual sync, no prune, and no deletion finalizer.
   Declare `homelab.davegallant.ca/backup-policy` as `scheduled` or
   `not-required`; `just lint` checks that decision against the central
   Schedule inventory. If the chart comes from an upstream Helm repository,
   that repository must be in the project's `sourceRepos`.
2. Namespace, before any sync. Argo CD does not create the destination
   namespace: no Application here uses `CreateNamespace=true`, and the
   `homelab` project's `clusterResourceWhitelist` is empty, so Argo CD
   cannot create Namespaces (or ClusterRoles) for it. A sync into a missing
   namespace fails with `namespaces "<name>" not found` and Argo CD does
   not retry it on its own; sync again only after the namespace exists.
   Create `kubernetes/apps/<service>/namespace.yaml` with the restricted
   Pod Security labels for the cluster's Kubernetes version (currently
   `restricted` with `enforce`/`audit`/`warn` at `v1.37`), then provision
   it by one of the established mechanisms — do not assume one is universal:
   hand-apply with `kubectl --context "$CTX" apply -f` (the k8s-readonly
   precedent, documented in that file's header), the
   `gitops_pod_security_namespaces` loop in
   `ansible/playbooks/talos-cluster/gitops-secrets.yml`, or an
   Argo-managed kustomization/policy Application that includes the file
   (tailnet-gateway, intel-gpu, forgejo-runner). A `namespace.yaml` sitting
   beside a chart is not Argo-managed unless a kustomization or policy
   Application includes it.
3. Chart values and Pod Security. If the namespace is `restricted`, the
   pod's container securityContext must satisfy it in full:
   `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`,
   `seccompProfile.type: RuntimeDefault`, and `runAsNonRoot: true`.
   Do not trust a chart's defaults here: a non-empty default
   securityContext is used verbatim by the template, so a chart's own
   restricted fallback (which only applies when the value is empty) never
   runs, and pod creation is forbidden with a `FailedCreate` naming the
   missing fields. Verify the rendered pod template, not just the values
   file. The same whitelist logic applies to other rendered kinds: a chart
   that creates a Secret by default (for example an OIDC Secret) fails
   under a project whose namespace whitelist excludes Secret, so disable
   unused Secret creation in values; likewise, do not enable a
   ClusterRoleBinding unless the app genuinely needs one — prefer
   per-user token RBAC (see step 7).
4. Tailnet Gateway route, if the app is tailnet-only. Add the namespace to
   the Gateway listener's `allowedRoutes.namespaces` selector in
   `kubernetes/apps/tailnet-gateway/gateway.yaml` (Gate 0 widening), add
   the HTTPRoute file under `kubernetes/apps/tailnet-gateway/` and list it
   in that directory's `kustomization.yaml`, and add the route namespace
   to the `homelab-tailnet-gateway` project's destinations. The route's
   backend Service must listen on pod IP, not loopback only.
5. Projects are applied, not synced. AppProjects are not reconciled by an
   Argo CD sync; apply them with `kubectl --context "$CTX" apply -f
   kubernetes/apps/argocd/project*.yaml` from the repo root, and confirm
   destinations, `sourceRepos`, and namespace/cluster resource whitelists
   cover every rendered kind and destination before syncing.
6. Sync order, manual, no prune, no force: `argocd` first (to register the
   new Application), then `tailnet-gateway` (to create the route), then
   the application itself. Verify Synced/Healthy at each step; a
   tailnet-gateway sync that failed before the namespace existed stays
   failed until it is explicitly retried, and its route stays Missing.
7. Headscale DNS, if the app gets a `*.tail.davegallant.ca` hostname.
   MagicDNS for the Gateway is not a wildcard: it is a per-hostname
   `extra_records` list in `ansible/playbooks/vps/headscale_config.yaml.j2`,
   each entry pointing at `100.100.0.8`. Add the app's record there,
   validate the rendered config with `headscale configtest` (using a
   `.yaml` filename), then apply it with the VPS Ansible run, which
   restarts Headscale only when the config changed. Pull remote `main`
   before running Ansible: a stale local template renders no change, so
   Headscale never restarts and the record never goes live. Verify from
   the operator's machine with `dig +short <app>.tail.davegallant.ca`
   (expected answer `100.100.0.8`, using a working hostname as a control).
   An empty dig answer while other hostnames resolve means the server has
   no record; flushing the local DNS cache cannot fix that. Flush only
   after dig works, if a browser still fails on a cached NXDOMAIN.
8. Login identity, if the app authenticates by token. Create the identity
   out of band, never in Git: a ServiceAccount, a ClusterRoleBinding to
   the `view` ClusterRole (never `cluster-admin`), and a short-lived
   token (`kubectl create token <sa> -n <namespace> --duration=24h`).
   Log in with that token and verify read-only behaviour (edit, delete,
   and scale forbidden) before declaring the app usable.
9. Monitoring is manual, not discovered. Gatus endpoints are configured
   per service in `ansible/playbooks/gatus/config/config.yaml`; a new
   app does not appear in Gatus until an endpoint entry is added and the
   Gatus config is redeployed. Absence from Gatus is not, by itself,
   evidence that the app is down. Add the entry following the existing
   pattern, using the MagicDNS domain directly when no `<service>_url`
   variable exists (as kiwix and arca do):

   ```
     - name: <service>
       url: "https://<service>.{{ headscale_magic_dns_domain }}/"
       <<: *defaults
   ```

   Then redeploy Gatus with its Ansible playbook (`hosts: gatus`); the
   commit alone does not change the live Gatus config, just as a
   Headscale template commit alone does not change live DNS. The
   endpoint-default conditions require `STATUS == 200` and a response
   under 5 seconds, so the chosen path must return 200 unauthenticated
   (a login page qualifies). The Gatus host (`tag:gatus`) is already
   allowed to the Gateway at `100.100.0.8:443` in the Headscale policy,
   so a tailnet URL check needs no policy change.

10. Homepage link, if the app should appear on the dashboard. Homepage
    links are also manual, not discovered: add the URL variable to
    `ansible/group_vars/all/vars.yaml`, map it in
    `kubernetes/apps/homepage/values.ansible.yaml.j2` as
    `HOMEPAGE_VAR_<SERVICE>_URL`, add the entry to
    `kubernetes/apps/homepage/config/services.yaml` (following the
    Headplane entry in the Infrastructure group), then run
    `just run talos-cluster/gitops-secrets` and restart the Homepage
    Deployment so its subPath mounts refresh. Homepage's ConfigMaps are
    Ansible-managed outside Argo CD, so an Argo sync alone never adds
    the link.

## Repository path cutover

When moving this tree from its former location under Ansible, publish the
complete move and all updated Application definitions in the same commit.
Existing cluster Applications retain their old source paths until explicitly
updated and may report comparison errors after the move reaches remote `main`.
Running workloads continue serving while those references are corrected.

After confirming the move is present on remote `main`, apply the restricted
monitoring, Velero, and Tailnet Gateway projects first. Then sync the Argo CD
Application definitions. Its source directory includes every Application,
including Argo CD itself. Once `victoriametrics`, `forgejo-backup`,
`velero-schedules`, and `tailnet-gateway` report their restricted projects, run
`argocd-project.yml`. It applies the narrowed platform project and ordinary
homelab project only after those Application project assignments pass its
assertions.

Use the intended context:

```sh
kubectl --context "$CTX" apply -f kubernetes/apps/argocd/project-monitoring.yaml
kubectl --context "$CTX" apply -f kubernetes/apps/argocd/project-velero-backup.yaml
kubectl --context "$CTX" apply -f kubernetes/apps/argocd/project-tailnet-gateway.yaml
kubectl --context "$CTX" apply -f kubernetes/apps/argocd/applications/argocd.yaml
```

After this one-time bootstrap, syncing `argocd` reconciles the Application
definitions. Review each Application comparison, then approve any workload
sync without prune or force.

## External resources

Secrets stay in Ansible Vault, never in Git values. From the repo root:

```sh
just run talos-cluster/gitops-secrets
```

The recipe defaults to the protected Talos kubeconfig and `ansible/.vault_pass`.
Set `KUBECONFIG` or `ANSIBLE_VAULT_PASSWORD_FILE` to override those paths.

This provisions the external resources declared in the playbook, including
application Secrets, the Velero Garage credential, and Homepage’s ConfigMaps
and icons. Check the workload runbook for any additional app-specific Secret
provisioning. Secret-bearing chart
renders exist only in process memory with
logging disabled. Homepage's `config/services.yaml`, `config/settings.yaml`,
icons, and `proxy-agent.cjs` remain the editable source. Its production chart
references those externally managed ConfigMaps. After editing that source,
run the resource playbook and restart the Homepage Deployment so its subPath
mounts refresh. If changing the tracked checksum, update `configChecksum` in
Homepage's production values and approve a sync. External Secret rotations
also require workload restarts. PostgreSQL password rotation additionally
requires changing the database role password.

The retired Argo CD sidecar PVCs stay outside the chart and remain
unmounted. They are retained for a later per-resource audit.

## Recovery and safeguards

The old application lifecycle playbooks and platform Helm installers check
Argo CD's tracking annotation and refuse mutations after handoff. Their
verification actions remain usable. Use Argo CD for normal rollback by
reverting Git and approving a sync. No database or local-PV data is moved by
this management change; existing Velero and Proxmox backup coverage remains.

Miniflux is removed; its chart and lifecycle playbook are retired from this
repository. Removing tracked configuration does not delete any retained live
volume data. Audit retained storage separately before deleting it.

For a fresh cluster, bootstrap Argo CD with `argocd.yml`, provision the external
resources and storage, apply all project definitions and the Applications,
then sync infrastructure before dependent workloads. Argo CD's self-managed
Application is synced last. The bootstrap remains available if Argo CD is
absent; it refuses to overwrite a running Argo-managed server. Deleting an
Application preserves its resources, so removing an Application alone is not
enough to hand its existing resources back to Helm: explicitly transfer their
ownership first. Never delete historical Helm records with `helm uninstall`.
