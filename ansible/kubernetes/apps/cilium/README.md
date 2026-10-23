# Cilium migration design

The Talos cluster currently uses Talos-managed Flannel with pod CIDR
`10.244.0.0/16` and VXLAN UDP 8472. Cilium is pinned to chart 1.20.3 and
will use cluster-pool IPAM with pod CIDR `10.245.0.0/16`, per-node `/24`
allocations, and VXLAN UDP 8473. Kube-proxy remains enabled; this avoids a
second dataplane change during the migration.

## Supported live-migration sequence

The [Cilium live-migration guide](https://docs.cilium.io/en/stable/installation/k8s-install-migration/)
requires a distinct pod CIDR, cluster-pool IPAM, and a distinct overlay
protocol or port. Install Cilium first in secondary mode with policy
enforcement disabled and no CNI configuration installed. A selector-based
`CiliumNodeConfig` opts individual nodes into Cilium. Migrate one node at a
time: cordon and drain it, label it for Cilium, restart its Cilium agent,
reboot it, verify its new pod IP and API reachability, then uncordon it.
Remove Flannel only after all nodes and pods have moved. The chart has
separate migration and steady-state values files for this transition.

Talos v1.14's [Cilium guide](https://docs.siderolabs.com/kubernetes-guides/cni/deploying-cilium)
uses a `KubeFlannelCNIConfig` delete patch to set CNI to `none`. That patch is
included in the generated control-plane and worker machine configs and will
be applied through the manual Talos Ansible flow. Cilium reuses Talos's
existing cgroup v2 and bpffs mounts; chart auto-mounting is disabled, the
cgroup root is `/sys/fs/cgroup`, and `SYS_MODULE` is omitted. kube-proxy stays
enabled, so KubePrism-specific kube-proxy replacement settings are not used.
Talos 1.14's [configuration changes](https://github.com/siderolabs/talos/releases/tag/v1.14.0)
also support pinning kubelet node IP selection to `192.168.1.0/24` with
`KubeNodeConfig`; this keeps the
reachable LAN address as the Kubernetes InternalIP when Cilium creates its
`cilium_host` interface. Secondary mode sets `cni.exclusive: false` so
Flannel's CNI file remains in place until each node is explicitly selected
through `CiliumNodeConfig`.

## Compatibility exit gate

The cluster runs Kubernetes v1.37.0. Cilium 1.20.3's tested compatibility
matrix lists Kubernetes 1.33 through 1.36; 1.37 is outside that tested range.
After the w-2 canary, the run stops and removes secondary-mode Cilium if the
connectivity suite fails in a way attributable to that pairing. Flannel and
all existing pod networking remain in place at that exit point.

The canary suite includes `cilium connectivity test`, a sidecar app's tailnet
HTTPS endpoint, and Hubble flow inspection. Alloy's existing w-2 readiness
shortfall is a recorded baseline and is not attributed to Cilium unless it
degrades from the measured starting state.

## Pod Security and resource placement

The `cilium-system` namespace has the privileged Pod Security enforcement
exception needed by Cilium's DaemonSet, matching the platform exception shape
used for Velero. Its audit and warn levels remain baseline. Cilium requests
192 MiB per agent and caps each at 256 MiB. The single operator and Hubble
Relay are pinned to the 4 GiB control-plane node; Relay requests 64 MiB. The
4 GiB w-1 is at 98% of requested memory at baseline, so neither component is
scheduled there. Before installation, compare w-2's measured workload use
and the `pve-g3-2` host memory gate in `provision-vms.yml`.

NetworkPolicies are deliberately disabled during dual-overlay migration.
After Flannel is removed, policies will be introduced one namespace at a
time. Every application Pod's policy includes its Tailscale sidecar's
control/relay traffic and Caddy's Cloudflare DNS-01/API traffic. Application
specific LAN exceptions are restricted to Garage S3, Loki, TrueNAS NFS, and
Homepage's documented proxy calls. Internet-fetching apps get world egress
with explicit LAN and cluster-range denies.

## Agent diagnostics without worker placement

`cilium.yml -e cilium_install_scope=control-plane` restricts the agent and
Envoy DaemonSets to `k8s-cp-1`. Operator and Relay already run there. This
secondary installation writes no CNI configuration and migrates no pods.
The worker-host memory checks apply to the default `cluster` scope; no
component is added to w-2 in the diagnostic scope. The migration values
enable pprof on localhost:6060 for a local kubectl port-forward.
Expand to the cluster scope only after the pve-g3-2 memory gate passes.

The control-plane diagnostic overlay raises only the agent memory limit to
512 MiB. At 256 MiB the agent cgroup recorded over 96,000 limit hits,
5.9 million direct page scans, 7,503 major faults, and sustained full
memory pressure without an OOM kill. Its main thread was in uninterruptible
sleep and localhost health/profiler requests timed out. This experiment
tests memory reclaim as the cause before attributing the stalls to the
Kubernetes version. The worker placement and limits are unchanged.
