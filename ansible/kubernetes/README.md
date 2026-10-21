# Kubernetes workloads

This repository stores Kubernetes workloads as raw manifests plus Ansible Jinja
templates. The Homepage pilot does not use Helm. Its source config remains in
`ansible/playbooks/homepage/config/`; the existing Homepage playbook continues
to own the LXC until a separately approved retirement.

## Homepage

The pilot runs Homepage, Caddy, and a Tailscale sidecar in one Pod. Tailscale
Serve forwards tailnet TCP 443 to Caddy on loopback port 8443. Caddy keeps the
existing Cloudflare DNS-01 certificate flow; Homepage is allowed at
`homepage.{{ headscale_magic_dns_domain }}`. The Tailscale node registered as
`homepage-k8s` for staging. The first cutover was rolled back after widget API
requests failed to reach private tailnet services. The desired Tailscale
hostname is in `apps/homepage/vars.yaml`.

The userspace Tailscale sidecar handles inbound HTTPS and exposes a local
outbound HTTP proxy. Homepage's Node preloader in `apps/homepage/proxy-agent.cjs`
routes requests to private tailnet hosts through that proxy, including the
TrueNAS WebSocket upgrade. Configured non-tailnet widget URL hosts connect
directly. Plain Node proxy
environment variables alone do not fix Homepage v2.6.0 because it constructs
custom HTTP agents. A kernel-mode Tailscale sidecar was tried with scoped
`NET_ADMIN`, `NET_RAW`, and `/dev/net/tun`, but Talos's cluster-wide Pod Security
baseline rejected the Pod. No Pod Security exception was applied. The preloader
is specific to Homepage's Node networking; future workloads need their own
outbound proxy support or another reviewed route.

Homepage's `/app/config` is a writable local PVC because the application writes
logs and generated files there. Ansible-managed `services.yaml` and
`settings.yaml` are mounted over that PVC from a ConfigMap. The custom icon
directory is a binary ConfigMap mounted at `/app/public/icons`. Tailscale state
and Caddy certificate state have separate local PVCs. All three PVs and the Pod
are pinned to `k8s-w-1` on `pve-g3-1`.

Edit the tracked `services.yaml`, `settings.yaml`, and icon files in
`ansible/playbooks/homepage/config/`; those remain Ansible-managed. The initial
runtime-config import streams the other live config files directly from the
Homepage LXC into the PVC, excluding those managed files, icons, logs, and Git
metadata. Their contents never enter the repository or a local temporary file.
For future edits to an imported file, add it to the repo as an Ansible-managed
template before changing it; until then, edit it on the PVC with `kubectl
cp`/`kubectl exec`. Edit Kubernetes resources under
`ansible/kubernetes/apps/homepage/`. The manual Ansible apply renders the Jinja files into a private temporary directory,
applies them to the explicitly confirmed current kubectl context, waits for the
rollout, confirms persistent Tailscale state, removes the one-use auth Secret,
and deletes the temporary render directory. Secret values are loaded from the
existing Ansible Vault variables; rendered Secret documents are never stored in
Git.

From `ansible/`, after the Talos cluster and its protected kubeconfig exist:

```sh
ansible-playbook playbooks/talos-cluster/apply-homepage.yml \
  -i inventory \
  --vault-password-file .vault_pass
```

The playbook prompts for the expected kubectl context. On first registration,
it creates a one-use Headscale preauth key through the repo's `pangolin` SSH
connection, holds the value only in Ansible memory and a short-lived Kubernetes
Secret, and removes the Secret after Tailscale identity persists across a pod
restart. Later applies reuse the PVC-backed identity. Do not run this playbook
in CI or as part of the normal all-host playbook list.

After the first deployment, import the remaining live Homepage config once:

```sh
ansible-playbook playbooks/talos-cluster/import-homepage-config.yml -i inventory
```

That playbook prompts for the expected context and requires typing `IMPORT`.
It streams the files over SSH and the Kubernetes API without displaying or
writing their contents to the checkout. It does not switch the tailnet hostname.

The hostname move is managed by `cutover-hostname.yml`; it renames the two
specific Headscale node IDs after checking that both are online. Headscale's
`given_name` is the MagicDNS label, while `name` remains the raw client
hostname. `verify-cutover.yml` confirms that the normal hostname resolves to
the Kubernetes tailnet IP and returns HTTP 200 with valid TLS. For immediate
rollback, run `rollback-hostname.yml` to return the existing hostname to the
still-running LXC, then change `apps/homepage/vars.yaml` back to
`homepage-k8s` before the next application rollout. All three playbooks require
the Vault password file. The verification playbook also requires the protected
Talos kubeconfig as `KUBECONFIG`.

From `ansible/`, the cutover and rollback commands are:

```sh
ansible-playbook playbooks/talos-cluster/cutover-hostname.yml \
  -i inventory --vault-password-file .vault_pass
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  ansible-playbook playbooks/talos-cluster/verify-cutover.yml \
  -i inventory --vault-password-file .vault_pass
ansible-playbook playbooks/talos-cluster/rollback-hostname.yml \
  -i inventory --vault-password-file .vault_pass
```

The rollback command is for recovery only; do not run it after a healthy
cutover. It changes the MagicDNS labels and leaves both machines running.
Run `verify-rollback.yml` after rollback to confirm the original LXC answers
the normal hostname over valid TLS.

## Capacity, backups, and observability

The pilot's VM layout is recorded in `cluster/README.md`. Keep the `pve-g3-2`
memory gate: inspect host availability and worker health before adding
workloads. `k8s-w-2` is at 2 GiB. Homepage's local data resides on `k8s-w-1`;
loss of that worker
means the dashboard is down until the worker returns or its data is restored
and deliberately relocated.

Proxmox `vzdump` is the first backup layer and includes all three Talos VMs;
that captures the worker's local PV data as part of its VM disk. A separate
off-host etcd snapshot is also taken through `snapshot-etcd.yml`. Before
retiring the LXC, verify secure recovery of Talos credentials and Ansible
Vault, and complete a tested procedure
for recovering the Homepage paths `/var/mnt/homepage/config`,
`/var/mnt/homepage/tailscale`, and `/var/mnt/homepage/caddy`. A full VM restore
must be isolated from the live cluster until node identity and etcd membership
are reconciled. The LXC remains the immediate application rollback target.

The Homepage pilot initially used `kubectl logs` and the Homepage file log.
The Alloy follow-up is prepared under `apps/alloy/`. It reads Kubernetes pod
logs through the Kubernetes API, with one non-root pod per node and no host
mounts. This respects Talos's Pod Security baseline. It does not collect
Talos node service logs or replace Beszel metrics. Each Alloy pod discovers
only pods on its own node and writes to the existing Loki instance over the
Grafana LXC's LAN address.

Loki has no authentication. The Grafana playbook's Docker firewall rule admits
TCP 3100 only from the three Talos node IPs in `cluster/vars.yaml`; existing
tailnet access stays in place. The Alloy apply playbook checks the configured
Grafana LAN address before mutating the cluster. The existing Grafana Alloy
process used about 85 MiB RSS and 0.2% CPU during inspection; the DaemonSet
requests 128 MiB and 50m CPU per node, with 256 MiB and 200m limits. Review
the 2 GiB worker's free memory after rollout.

Apply these as two separately approved actions: first run the Grafana playbook
to admit the Talos node IPs to Loki; then run the Alloy playbook to create the
namespace, RBAC, ConfigMap, and DaemonSet. The Alloy playbook is manual; the
Grafana playbook is also part of the normal all-host CI run, so merging this
branch will reapply its firewall rule. From `ansible/`:

```sh
ansible-playbook playbooks/grafana/main.yml -i inventory \
  --vault-password-file .vault_pass
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  ansible-playbook playbooks/talos-cluster/apply-alloy.yml \
  -i inventory -e talos_kube_context=admin@homelab
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  ansible-playbook playbooks/talos-cluster/verify-alloy.yml -i inventory
```

If Alloy causes trouble, run `remove-alloy.yml` with the same kubeconfig and
explicit context to remove its DaemonSet while leaving Homepage running. A
separate approved Grafana playbook run after removing the source-and-port rule
from the repo closes the LAN path again. The Alloy RBAC and ConfigMap can stay
for troubleshooting until their removal is separately approved.
