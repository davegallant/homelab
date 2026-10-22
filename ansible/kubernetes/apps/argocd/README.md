# Argo CD bootstrap and BentoPDF handoff

Ansible installs Argo CD from the pinned upstream Helm chart and provisions
application Secrets from Vault. Argo CD reads desired application state from
`https://github.com/davegallant/homelab.git`, branch `main`. Forgejo remains a
recovery mirror. Argo CD polls for commits; every application sync requires
manual approval. There is no automated sync, pruning, or deletion finalizer.

The initial installation is a single controller, repo server, API server and
Redis. Dex and notifications are disabled; ApplicationSet has zero replicas.
All images have version and digest pins. The server is a ClusterIP Service
with its default TLS and admin authentication. No public ingress or additional
Tailscale identity is required. Resource requests total 352Mi of memory;
revisit sizing as applications are added.

## Bootstrap

From the repository root:

```sh
export KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig"
ansible-playbook ansible/playbooks/talos-cluster/argocd.yml \
  -i ansible/inventory --vault-password-file ansible/.vault_pass
ansible-playbook ansible/playbooks/talos-cluster/bentopdf-secret.yml \
  -i ansible/inventory --vault-password-file ansible/.vault_pass
```

Both playbooks explicitly target `admin@homelab`; override with
`-e talos_kube_context=...` if the kubeconfig context has been renamed.
The Secret playbook streams base64-encoded Vault data to Kubernetes through
stdin with Ansible logging disabled. It creates `bentopdf-newt-external`;
the currently Helm-owned `bentopdf-newt` remains available during handoff.

Access the UI through a local port-forward:

```sh
kubectl --context admin@homelab -n argocd port-forward service/argocd-server 8080:443
```

Open `https://localhost:8080` and accept the local self-signed certificate.
Log in as `admin`. Retrieve the initial password in a private terminal:

```sh
kubectl --context admin@homelab -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

Change the admin password through the UI and remove the initial-password
Secret after confirming the new password works. Never put credentials in Git.

## First application

First commit and push the chart, `../bentopdf/values.production.yaml`, and
the Argo CD definitions. Pushing requires Dave's explicit request. Verify
remote `main` contains those files before registering the Application;
the controller cannot read local unpushed commits.

Then register the committed Application:

```sh
kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/bentopdf.yaml
kubectl --context admin@homelab -n argocd get application bentopdf
```

Open BentoPDF's diff in Argo CD. Require a successful comparison against the
intended remote commit. Expected resources are `Deployment/bentopdf`,
`Service/bentopdf`, and `Schedule/bentopdf-daily` in `velero`. The Deployment
keeps its current image pins and selects the external Newt Secret. The
restricted `homelab` project permits only these resource kinds and the two
destination namespaces; Secrets remain owned by Ansible.

Approve **Sync** with pruning and force disabled. The existing Deployment
uses Recreate, so switching the Secret reference briefly restarts BentoPDF
and its Newt tunnel. Require Synced/Healthy and verify the existing public
BentoPDF URL. Future updates are Git commits followed by approved syncs.
Secrets must exist before syncing; rotating the external Secret requires
restarting the Deployment to refresh its environment variables.

## Ownership and recovery

Argo CD renders Helm templates; it does not upgrade the existing Helm release.
Keep the historical release records during the first handoff, but never run
`helm uninstall bentopdf`: it would delete resources now managed by Argo CD.
The legacy `bentopdf.yml` playbook refuses mutations once the Deployment has
an Argo CD tracking annotation; its read-only verify action remains usable.
After the handoff is accepted, retire the migration playbook and old
Helm-owned Secret/records in a separate explicit cleanup.

For a workload rollback, revert its Git configuration and approve another
sync. Deleting the Application preserves BentoPDF because it has no deletion
finalizer. If Argo CD itself is lost, rerun the bootstrap and Secret playbooks,
then reapply the Application from Git. Argo CD has no persistent data volume;
Git plus Ansible Vault hold its desired application configuration and secrets.
The local Argo CD admin password is cluster state and must be reset on a
fresh installation. BentoPDF remains covered by its existing Velero schedule.

Upstream references: [Helm integration](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/),
[declarative applications](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/).
