# Cilium CNI and network operations

## Current cluster state

The Talos cluster runs Kubernetes `1.37.0` with Cilium chart `1.20.3` as its
primary CNI. Cluster-pool IPAM assigns `10.245.0.0/16` (`/24` per node) and
VXLAN uses UDP `8473`. Flannel has been removed and kube-proxy remains enabled.
Talos machine configuration sets `cluster.network.cni.name: none`; Cilium
reuses Talos's cgroup v2 and bpffs mounts, sets the cgroup root to
`/sys/fs/cgroup`, and omits `SYS_MODULE`.

All three nodes are Ready and every pod-network workload has a Cilium
endpoint; host-network pods are outside endpoint policy. Cilium
agents, operator, Relay and UI are healthy. Hubble Relay reports 3/3 connected
nodes.

## Pod Security and resource placement

The `cilium-system` namespace has privileged Pod Security enforcement for the
CNI DaemonSet, matching the exception shape used by Velero; audit and warn
remain baseline. These labels are in `namespace.yaml`. Cilium agents request
192 MiB and cap at 512 MiB. Operator, Relay, and UI are pinned to
`k8s-cp-1`. `k8s-w-2` was raised to 2.5 GiB through the Ansible VM flow after
checking the `pve-g3-2` host memory gate.

Default-deny policies are now active. Each app policy lives in that app's
directory and is applied with `playbooks/talos-cluster/cilium-apply-policy.yml`.
Application policies allow same-namespace traffic, kube-dns on TCP/UDP 53,
and documented external dependencies. They do not grant the `cluster` entity:
that entity includes other pods, nodes, and the Kubernetes API, bypassing
CIDR-based restrictions for managed cluster identities. Infrastructure
controllers get explicit `kube-apiserver` access on TCP 443/6443. Relay/UI
can reach Cilium agents on TCP 4244.

Sidecar egress includes Tailscale control/relay and Cloudflare DNS-01/API.
Internet-fetching namespaces (`changedetection`, `miniflux`, `searxng`)
retain explicit LAN and cluster-range denies. Homepage and Kiwix retain
single-host TrueNAS exceptions. Alloy can reach the API, node metrics on
TCP 10250/9100/9964, CoreDNS metrics on TCP 9153, kube-state-metrics on TCP
8080, Loki on TCP 3100, and VictoriaMetrics on TCP 8428. Velero can reach
the API and Garage S3 on TCP 3900. Argo CD retains HTTPS egress for GitHub
and configured chart repositories.

The NFS CSI policy selects only the controller in shared `kube-system`.
The current controller and node plugins use host networking, which endpoint
policies do not isolate. These policies also do not restrict destinations
inside userspace Tailscale/Newt tunnels. See the policy inventory in
`kubernetes/README.md`.

## Primary CNI, Vault ownership, and Argo CD adoption

`cilium-primary.yml` completed the transition after every pod-network pod
verified as a Cilium endpoint. It recorded Helm retention for the three
generated TLS Secrets, materialized their existing contents from encrypted
Vault using the ansible-vault field manager, then applied steady-state values.
The steady chart references existing TLS Secrets and renders no Secrets.
The certificates were imported intact; no private key or certificate data
was printed. Certificate renewal must update Vault and rematerialize these
Secrets before expiration; Helm/Argo no longer regenerates them.

`cilium-adopt.yml` applied the platform permissions and rendered Cilium
Application, then requested one manual sync without pruning. The Application
template embeds the repository values as valuesObject, so adoption does
not require pushing unreviewed main changes to the live-host CI pipeline.
The chart version still comes from vars.yaml. Future Cilium value changes
use the adoption playbook to update the Application and manually sync it.

The bootstrap remains the recovery path: use `cilium.yml` with
`cilium_bootstrap_mode=steady` and `cilium_recovery=true` only for explicit
recovery when Argo is unavailable. This rematerializes TLS from Vault,
installs the pinned steady-state chart, and bypasses the healthy-base
checks that cannot pass during a CNI failure. Normal runs refuse to
overwrite resources already tracked by Argo CD.

`rollOutCiliumPods: true` makes the chart checksum its ConfigMap into the
agent pod template. Config changes therefore restart agents one at a time
(`maxUnavailable: 1`). A healthy DaemonSet alone does not prove a changed
ConfigMap has been consumed: check the running agent's PolicyEnforcement
value is `default` rather than `never` after a Cilium values change.

## Hubble UI

The steady-state values enable Hubble UI on `k8s-cp-1`, with a ClusterIP
service. Apply changes with `cilium-adopt.yml`; it requests a manual Argo CD
sync without pruning. The chart pins both UI images by version and digest.

Access it locally:

```sh
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  kubectl --context admin@homelab -n cilium-system port-forward \
  --address 127.0.0.1 svc/hubble-ui 12000:80
```

Open <http://localhost:12000>. The UI uses Hubble Relay for flow data.

Hubble Relay CLI access uses the same localhost-only pattern:

```sh
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  kubectl --context admin@homelab -n cilium-system port-forward \
  --address 127.0.0.1 svc/hubble-relay 4245:80
hubble status
hubble observe --namespace changedetection --last 50
```
