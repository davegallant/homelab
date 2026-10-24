# Kubernetes security and network policy

- **Cilium CNI (completed 2026-10-23).** All three Talos nodes run Cilium
  `1.20.3` with cluster-pool IPAM on `10.245.0.0/16` (`/24` per node) and
  VXLAN UDP `8473`. Flannel has been removed; kube-proxy remains enabled.
  Kubernetes is `1.37.0`, outside Cilium 1.20.3's tested `1.33–1.36` matrix.
  The dual-overlay migration and observed compatibility evidence are recorded
  in [`apps/cilium`](apps/cilium/README.md).
- **Default-deny policies.** Each policy is stored beside its workload and
  applied through `playbooks/talos-cluster/cilium-apply-policy.yml`. App
  policies allow cluster DNS, intra-namespace traffic, the documented app
  dependencies, and the sidecar's Tailscale/Cloudflare egress. Internet
  fetchers explicitly deny LAN and cluster CIDRs. Homepage and Kiwix have a
  single TrueNAS host exception; Alloy has only its Loki and VictoriaMetrics
  targets; Velero has only Garage S3. The live inventory is: `changedetection`,
  `miniflux`, `searxng`, `bentopdf`, `homepage`, `kiwix`, `lubelogger`,
  `maloja`, `seerr`, `alloy`, `monitoring`, `argocd`, `velero`,
  `local-path-storage`, `cilium-system`, and a CSI-controller-only policy in
  shared `kube-system`. The NFS CSI node plugin uses host networking, so its
  node-side NFS mount is verified with a fresh PVC smoke test rather than
  treated as pod egress.
- **Hubble access.** Hubble Relay is a ClusterIP in `cilium-system`. For the
  CLI, port-forward `service/hubble-relay` from `4245:80`; `hubble status`
  then reports the connected agents and `hubble observe` shows flows. The UI
  is also enabled and can be opened with a localhost-only port-forward from
  `service/hubble-ui` `12000:80` at <http://localhost:12000>.
- **Pod Security exception.** `cilium-system` has privileged enforcement for
  the CNI DaemonSet, with audit and warn kept at baseline, matching the
  platform-exception shape used by Velero. The namespace is managed in
  `apps/cilium/namespace.yaml`.
- **Phase verification.** Nodes are Ready on Kubernetes `1.37.0`; Cilium
  agents and Relay are healthy on all nodes; every pod-network workload is a
  Cilium endpoint. Homepage and changedetection migration backups completed
  with completed PodVolumeBackups. The full `cilium connectivity test` did
  not complete reliably because its temporary echo pods failed readiness; no
  failure was isolated to the Kubernetes 1.37 pairing. Hubble showed the
  documented Loki/metrics/Garage flows forwarded and denied direct LAN and
  SSDP/Tailscale peer-discovery attempts; app HTTPS checks passed through the
  permitted sidecar path.

- **Kyverno: deferred.** Admission policy via Kyverno was considered and set
  aside: Argo CD AppProject whitelists, Pod Security baseline labels, and
  digest-pinned images already cover the admission side at this scale.
  Revisit if image signature verification (cosign) is wanted or repo review
  becomes the bottleneck.

[Back to Kubernetes overview](README.md).
