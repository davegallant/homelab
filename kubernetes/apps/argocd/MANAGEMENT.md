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
resource kinds required by infrastructure charts. All Applications require
manual sync except the qBittorrent egress guardrail; none has pruning or a
deletion finalizer.
Upstream charts use multiple sources: a pinned chart plus values from GitHub
`main`. Custom charts read their sibling `values.production.yaml`.

Edit values, chart templates, and Application definitions in Git, push, review
the Argo CD diff, then approve Sync without prune or force. Syncing `argocd`
updates Application definitions; sync each changed workload separately.
Storage objects outside the charts are
not adopted or recreated. Namespace Pod Security labels are preserved.
Use server-side apply for the platform charts, including their large CRDs.

## Repository path cutover

When moving this tree from its former location under Ansible, publish the
complete move and all updated Application definitions in the same commit.
Existing cluster Applications retain their old source paths until explicitly
updated and may report comparison errors after the move reaches remote `main`.
Running workloads continue serving while those references are corrected.

After confirming the move is present on remote `main`, apply the restricted
monitoring and Velero projects first. Then apply the updated Argo CD Application
to enable Git-managed Application definitions and sync it. Its source directory
includes every Application definition, including Argo CD itself. Once the
`victoriametrics` and `forgejo-backup` Applications report their new projects,
run `argocd-project.yml` to remove `monitoring` and `velero` from the ordinary
`homelab` destinations. That playbook refuses this final step until both
Applications have moved.

Use the intended context:

```sh
kubectl --context "$CTX" apply -f kubernetes/apps/argocd/project-monitoring.yaml
kubectl --context "$CTX" apply -f kubernetes/apps/argocd/project-velero-backup.yaml
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

The retired Kiwix and Miniflux LXC playbooks are excluded from daily CI and
the all-host playbook list. Their stopped containers and tracked Compose
files are historical recovery material, not current deployment targets.

For a fresh cluster, bootstrap Argo CD with `argocd.yml`, provision the external
resources and storage, apply all project definitions and the Applications,
then sync infrastructure before dependent workloads. Argo CD's self-managed
Application is synced last. The bootstrap remains available if Argo CD is
absent; it refuses to overwrite a running Argo-managed server. Deleting an
Application preserves its resources, so removing an Application alone is not
enough to hand its existing resources back to Helm: explicitly transfer their
ownership first. Never delete historical Helm records with `helm uninstall`.
