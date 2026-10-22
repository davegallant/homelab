# Argo CD bootstrap and BentoPDF handoff

The full release inventory and ongoing workflow are in
[`MANAGEMENT.md`](MANAGEMENT.md). All releases now have Application definitions,
including Argo CD itself; the bootstrap below remains the recovery path.

Ansible installs Argo CD from the pinned upstream Helm chart and provisions
application Secrets from Vault. Argo CD reads desired application state from
`https://github.com/davegallant/homelab.git`, branch `main`. Forgejo remains a
recovery mirror. Argo CD polls for commits; every application sync requires
manual approval. There is no automated sync, pruning, or deletion finalizer.

The installation is a single controller, repo server, API server and Redis.
Dex and notifications are disabled; ApplicationSet has zero replicas.
All images have version and digest pins. The server remains a ClusterIP
Service and runs with `--insecure`: Caddy owns TLS. Tailscale and Caddy run
as extra containers in the upstream chart's server Pod, using the same
userspace pattern as Homepage and Kiwix. Tailscale Serve forwards tailnet
TCP 443 to Caddy at `127.0.0.1:8443`; Caddy obtains its certificate through
Cloudflare DNS-01 and proxies to Argo CD at `http://127.0.0.1:8080`.
There is no Pangolin/Newt tunnel, public ingress, NodePort or LoadBalancer.
Requests total 448Mi of memory; revisit sizing as applications are added.

The URL is `https://argocd.<headscale_magic_dns_domain>`. The domain and
Headscale login server come from Ansible variables. The Cloudflare token
is streamed from Vault into `argocd-caddy`, without writing it locally.
`argocd-tailscale` and `argocd-caddy` are Retain-policy local-path PVCs for
the tailnet identity and certificate state. They bind the server Pod to
one worker; Recreate prevents two Pods from sharing the live identity.
First registration uses a one-use Headscale key, removed from Kubernetes
after verification. The bootstrap then restarts the Pod and checks the
same tailnet address again without the key.

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

Use the tailnet URL printed by the bootstrap playbook. For local diagnostic
access without the proxy, port-forward the HTTP server:

```sh
kubectl --context admin@homelab -n argocd port-forward service/argocd-server 8080:80
```

The diagnostic URL is `http://localhost:8080`; normal tailnet access uses
trusted HTTPS. Log in as `admin`. Retrieve the initial password in a private terminal:

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
then reapply the Application from Git. Git plus Ansible Vault hold the
desired application configuration and secrets; the proxy PVCs hold runtime
tailnet identity and certificate state.
The local Argo CD admin password is cluster state and must be reset on a
fresh installation. Tailnet identity and certificate state are node-local
PVCs covered by the worker VM backup. Do not clone the live tailnet identity
into a restore drill; use a new identity if relocating the service. Caddy
can reissue certificates when necessary. BentoPDF remains covered by its
existing Velero schedule. Changes to the tailnet ConfigMap trigger a server
rollout through its checksum annotation; after rotating the Cloudflare token,
restart the server to refresh its subPath-mounted credential.

Upstream references: [Helm integration](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/),
[declarative applications](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/).
