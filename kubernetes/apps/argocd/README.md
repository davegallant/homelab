# Argo CD operations and recovery

The ongoing deployment workflow and ownership safeguards are in
[`MANAGEMENT.md`](MANAGEMENT.md). All releases now have Application definitions,
including Argo CD itself; the bootstrap below remains the recovery path.

For bootstrap, Ansible installs Argo CD from the pinned upstream Helm chart and provisions
application Secrets from Vault. Argo CD reads desired application state from
`https://github.com/davegallant/homelab.git`, branch `main`. Forgejo remains a
recovery mirror. Argo CD polls for commits; every application sync requires
manual approval. There is no automated sync, pruning, or deletion finalizer.

The installation is a single controller, repo server, API server and Redis.
Dex and notifications are disabled; ApplicationSet has zero replicas.
All images have version and digest pins. The server remains a ClusterIP
Service and runs with `--insecure`; the central Cilium Gateway terminates
trusted HTTPS and routes browser HTTP through an HTTPRoute to `argocd-server:80`.
CLI gRPC uses a GRPCRoute to the Service's separate h2c port 8080, with Cilium
Gateway ALPN enabled for HTTP/2 negotiation. Both ports target the server pod's
8080 listener. There is no Tailscale sidecar,
Pangolin/Newt tunnel, public ingress, NodePort or LoadBalancer.

## Administrator access

The built-in `admin` account remains enabled and is the only Argo CD login
configured here. It has full Argo CD access. The Kubernetes admin kubeconfig
and Talos credentials are separate maintenance credentials. Argo CD remains
reachable only through the tailnet Gateway; keep its admin password unique and
high-entropy. Repository and deployment account MFA remain separate controls.

The URL is `https://argocd.tail.davegallant.ca`. The old `argocd-tailscale`
and `argocd-caddy` Retain-policy PVCs are unmounted and retained for a later
per-resource audit; they are not needed by the server pod.

## Recovery bootstrap

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
stdin with Ansible logging disabled. It creates `bentopdf-newt-external`
for the workload.

Use the Gateway URL printed by the bootstrap playbook. For local diagnostic
access, port-forward the HTTP server:

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

## Ownership and recovery

Argo CD renders Helm templates; it does not upgrade the existing Helm release.
Do not run Helm mutations against resources managed by Argo CD. Legacy
lifecycle playbooks refuse mutations once an Argo tracking annotation exists.

For a workload rollback, revert its Git configuration and approve another
sync. Deleting the Application preserves BentoPDF because it has no deletion
finalizer. If Argo CD itself is lost, rerun the bootstrap and Secret playbooks,
then reapply the Application from Git. Git plus Ansible Vault hold the
desired application configuration and secrets. The local Argo CD admin
password is cluster state and must be reset on a fresh installation.
BentoPDF remains covered by its existing Velero schedule.

Upstream references: [Helm integration](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/),
[declarative applications](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/).
