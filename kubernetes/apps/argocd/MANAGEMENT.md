# Release management

Application definitions cover service workloads and cluster infrastructure,
including Argo CD itself. See the [workload index](../../README.md) and the
tracked [Application definitions](applications/) for the current inventory.
Charts remain Helm templates, while Argo CD owns their deployed resources. Historical Helm
release records are retained for reference; `helm list` is not an ownership
inventory. Do not run `helm upgrade`, `helm rollback`, or `helm uninstall`
against these releases.

Application definitions live in `applications/`, except the first BentoPDF
definition at `bentopdf.yaml`. The `homelab` project owns service applications. `homelab-platform` permits
the pinned upstream repositories and
the cluster resource kinds required by infrastructure charts. All Applications
require manual sync; none has automated sync, pruning, or a deletion finalizer.
Upstream charts use multiple sources: a pinned chart plus values from GitHub
`main`. Custom charts read their sibling `values.production.yaml`.

Edit values and chart templates in Git, push, review the Argo CD diff, then
approve Sync without prune or force. Storage objects outside the charts are
not adopted or recreated. Namespace Pod Security labels are preserved.
Use server-side apply for the platform charts, including their large CRDs.

## Repository path cutover

When moving this tree from its former location under Ansible, publish the
complete move and all updated Application definitions in the same commit.
Existing cluster Applications retain their old source paths until explicitly
updated and may report comparison errors after the move reaches remote `main`.
Running workloads continue serving while those references are corrected.

After confirming the move is present on remote `main`, apply the definitions
from the repository root using the intended context:

```sh
kubectl --context "$CTX" apply -f kubernetes/apps/argocd/bentopdf.yaml
kubectl --context "$CTX" apply -f kubernetes/apps/argocd/applications/ \
  --recursive=false
```

The directory command applies the `.yaml` Application definitions. Cilium's
`.yaml.j2` definition is rendered separately through
`ansible/playbooks/talos-cluster/cilium-adopt.yml`; its chart is upstream and
its values are inline, so the move does not change its remote source path.
Review each Application comparison, then approve any needed sync without
prune or force. Apply definitions only after the new source paths are available.

## External resources

Secrets stay in Ansible Vault, never in Git values. From the repo root:

```sh
just run talos-cluster/gitops-secrets
```

The recipe defaults to the protected Talos kubeconfig and `ansible/.vault_pass`.
Set `KUBECONFIG` or `ANSIBLE_VAULT_PASSWORD_FILE` to override those paths.

This provisions the external resources declared in the playbook, including
application Secrets, the Velero Garage credential, Argo CD’s Cloudflare
credential, and Homepage’s ConfigMaps and icons. Check the workload runbook
for any additional app-specific Secret provisioning. Secret-bearing chart
renders exist only in process memory with
logging disabled. Homepage's `config/services.yaml`, `config/settings.yaml`,
icons, and `proxy-agent.cjs` remain the editable source. Its production chart
references those externally managed ConfigMaps. After editing that source,
run the resource playbook and restart the Homepage Deployment so its subPath
mounts refresh. If changing the tracked checksum, update `configChecksum` in
Homepage's production values and approve a sync. External Secret rotations
also require workload restarts. PostgreSQL password rotation additionally
requires changing the database role password.

The Argo CD tailnet ConfigMap remains Ansible-managed. After editing it, run
the resource playbook, update `server.podAnnotations.checksum/tailnet` in
Argo CD's production values to its rendered SHA-256, and approve a sync.
The Argo CD sidecar PVCs and one-use registration workflow stay outside its
chart. Preserve the existing PVC-backed identities during upgrades.

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
resources and storage, apply both project definitions and the Applications,
then sync infrastructure before dependent workloads. Argo CD's self-managed
Application is synced last. The bootstrap remains available if Argo CD is
absent; it refuses to overwrite a running Argo-managed server. Deleting an
Application preserves its resources, so removing an Application alone is not
enough to hand its existing resources back to Helm: explicitly transfer their
ownership first. Never delete historical Helm records with `helm uninstall`.
