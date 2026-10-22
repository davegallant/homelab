# Release management

All eleven installed Helm releases are represented as Argo CD Applications:
BentoPDF, SearXNG, Miniflux, Homepage, Kiwix, node exporter, kube-state-metrics,
metrics-server, NFS CSI, Velero, and Argo CD itself. Charts remain Helm
templates, while Argo CD owns their deployed resources. Historical Helm
release records are retained for reference; `helm list` is not an ownership
inventory. Do not run `helm upgrade`, `helm rollback`, or `helm uninstall`
against these releases.

Application definitions live in `applications/`, except the first BentoPDF
definition at `bentopdf.yaml`. The `homelab` project owns the five service
applications. `homelab-platform` permits the pinned upstream repositories and
the cluster resource kinds required by infrastructure charts. All Applications
require manual sync; none has automated sync, pruning, or a deletion finalizer.
Upstream charts use multiple sources: a pinned chart plus values from GitHub
`main`. Custom charts read their sibling `values.production.yaml`.

Edit values and chart templates in Git, push, review the Argo CD diff, then
approve Sync without prune or force. Storage objects outside the charts are
not adopted or recreated. Namespace Pod Security labels are preserved.
Use server-side apply for the platform charts, including their large CRDs.

## External resources

Secrets stay in Ansible Vault, never in Git values. From the repo root:

```sh
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  ansible-playbook ansible/playbooks/talos-cluster/gitops-secrets.yml \
  -i ansible/inventory --vault-password-file ansible/.vault_pass
```

This provisions external Secrets for all five services, the existing Velero
Garage credential, Argo CD's Cloudflare credential, and Homepage's config maps
and icons. Secret-bearing chart renders exist only in process memory with
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

For a fresh cluster, bootstrap Argo CD with `argocd.yml`, provision the external
resources and storage, apply both project definitions and the Applications,
then sync infrastructure before dependent workloads. Argo CD's self-managed
Application is synced last. The bootstrap remains available if Argo CD is
absent; it refuses to overwrite a running Argo-managed server. Deleting an
Application preserves its resources, so removing an Application alone is not
enough to hand its existing resources back to Helm: explicitly transfer their
ownership first. Never delete historical Helm records with `helm uninstall`.
