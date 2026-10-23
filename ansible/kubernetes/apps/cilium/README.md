# Cilium CNI migration and operations

## Current cluster state

The Talos cluster runs Kubernetes `1.37.0` with Cilium chart `1.20.3` as its
primary CNI. Cluster-pool IPAM assigns `10.245.0.0/16` (`/24` per node) and
VXLAN uses UDP `8473`. Flannel has been removed and kube-proxy remains enabled.
Talos machine configuration sets `cluster.network.cni.name: none`; Cilium
reuses Talos's cgroup v2 and bpffs mounts, sets the cgroup root to
`/sys/fs/cgroup`, and omits `SYS_MODULE`.

All three nodes are Ready. The migration verified every pod-network workload
as a Cilium endpoint; host-network pods are outside endpoint policy. Cilium
agents, operator, Relay and UI are healthy. Hubble Relay reports 3/3 connected
nodes. The rollout and its remaining connectivity-test limitation are recorded
below.

## Live-migration sequence (completed 2026-10-23)

The run followed the [Cilium live-migration guide](https://docs.cilium.io/en/stable/installation/k8s-install-migration/):
Cilium 1.20.3 was installed first in secondary mode with cluster-pool IPAM,
a separate pod CIDR, VXLAN UDP 8473, and policy enforcement disabled. A
selector-based `CiliumNodeConfig` migrated one node at a time. `k8s-w-2` was
the canary, followed by `k8s-w-1` and `k8s-cp-1`; each node was health-gated
before proceeding. Flannel was removed only after all pod-network workloads
had moved. Migration and steady-state values remain separate in this app.

Talos v1.14's [Cilium guide](https://docs.siderolabs.com/kubernetes-guides/cni/deploying-cilium)
uses a `KubeFlannelCNIConfig` delete patch to set CNI to `none`. The repo's
generated control-plane and worker configs carry that change through the
manual Talos Ansible flow. Kube-proxy replacement was not selected, so
KubePrism-specific kube-proxy values are not used.
Talos 1.14's [configuration changes](https://github.com/siderolabs/talos/releases/tag/v1.14.0)
also support pinning kubelet node IP selection to `192.168.1.0/24` with
`KubeNodeConfig`; this keeps the reachable LAN address as the Kubernetes
InternalIP when Cilium creates its `cilium_host` interface. Secondary mode
set `cni.exclusive: false`, leaving Flannel's CNI file in place until each
node was explicitly selected through `CiliumNodeConfig`.

## Compatibility exit gate

At the time of the migration, Cilium 1.20.3's tested compatibility matrix
listed Kubernetes 1.33 through 1.36; this cluster's Kubernetes 1.37.0 pairing
was outside that tested range. The w-2 canary passed node health, Cilium
endpoint, sidecar HTTPS, and Hubble checks. The full `cilium connectivity
test` did not complete reliably: temporary echo pods failed readiness and the
suite stalled. No failure was isolated to the Kubernetes 1.37 pairing. The
test namespaces were cleaned up. Direct workload, DNS, Hubble flow, NFS, and
backup checks were used for rollout gates; the full CLI suite remains
unverified. Alloy's w-2 readiness shortfall pre-dated migration.

## Pod Security and resource placement

The `cilium-system` namespace has privileged Pod Security enforcement for the
CNI DaemonSet, matching the exception shape used by Velero; audit and warn
remain baseline. These labels are in `namespace.yaml`. Cilium agents request
192 MiB and cap at 512 MiB. Operator, Relay, and UI are pinned to
`k8s-cp-1`. `k8s-w-2` was raised to 2.5 GiB through the Ansible VM flow after
checking the `pve-g3-2` host memory gate.

Default-deny policies are now active. Each app policy lives in that app's
directory and is applied with `playbooks/talos-cluster/cilium-apply-policy.yml`.
They allow same-namespace traffic, kube-dns, cluster access, and documented
dependencies. The sidecar egress includes Tailscale control/relay and
Cloudflare DNS-01/API. Internet-fetching namespaces (`changedetection`,
`miniflux`, `searxng`) have explicit LAN and cluster-range denies. Homepage
and Kiwix have a single TrueNAS host exception; Alloy is limited to Loki
`:3100`, VictoriaMetrics `:8428`, and kubelet metrics; Velero is limited to
Garage S3 `:3900`. Argo CD has HTTPS egress for GitHub and configured chart
repositories. The NFS CSI policy selects only the controller in shared
`kube-system`; its privileged node plugin uses host networking. See the
policy inventory in `ansible/kubernetes/README.md`.

## Agent memory investigation and placement

During pre-migration diagnostics, a 256 MiB agent limit caused reclaim
thrashing; increasing the limit to 512 MiB restored Ready status and Hubble
health. The steady-state chart uses that 512 MiB limit with a 192 MiB
request. The w-2 VM was raised to 2.5 GiB through the Talos Ansible VM flow
after the `pve-g3-2` memory gate passed. The agent and Envoy DaemonSets now
run on all three nodes; operator, Relay, and UI remain on the control plane.

## Migration and connectivity playbooks

The completed node order was w-2 canary, w-1, then cp-1. The repo retains
`cilium-migrate-node.yml`, `cilium-remove-flannel.yml`, and
`cilium-connectivity.yml` for diagnosis and recovery. Connectivity test
namespaces were cleaned up. The full CLI suite did not finish because its
temporary echo pods failed readiness; it is not recorded as passing. The
run found no failure attributable to Kubernetes 1.37. App URL checks,
endpoint validation, NFS/PVC smoke, backups, and Hubble flow inspection
passed their gates.

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
