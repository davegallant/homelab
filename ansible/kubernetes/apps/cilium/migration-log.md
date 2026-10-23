# Cilium migration evidence — 2026-10-22

## Secondary installation and w-2 canary

- Talos v1.14.1; actual Kubernetes v1.37.0; Cilium chart 1.20.3.
- All three secondary agents and Envoy pods Ready; operator and Relay Ready;
  `cilium status` reports OK. Kube-proxy remains enabled.
- Agent 256 MiB cap caused direct memory reclaim and stalled health probes.
  Raising it to 512 MiB restored health; a fresh agent started Ready without
  a restart. This was not established as a Kubernetes compatibility failure.
- Talos `KubeNodeConfig.nodeIP.validSubnets` pins the LAN node IPs, preventing
  selection of the newly created cilium_host address.
- w-2 VM increased from 2288 to 2560 MiB through `resize-worker.yml`; the
  Proxmox host memory gate passed. Kubernetes capacity changed from
  2170340 KiB to 2441544 KiB. Its existing 25 GiB disk was not full.
- Argo CD controller and repo-server moved to cp-1 through its Application
  and manual sync. The Linux node selector is retained to avoid SSA drift.
- w-2 migrated first using CiliumNodeConfig, an agent restart, and a Talos
  reboot. The node returned Ready; 05-cilium.conflist is active and Flannel's
  file is renamed .cilium_bak. Batch A pods have ready Cilium endpoints
  on 10.245.1.0/24. changedetection's tailnet HTTPS URL returned 200.
- Canary connectivity play completed successfully. Unaffected no-policy
  scenarios and health checks passed strict flow validation. The Service
  scenario passed its actual requests and the explicit Hubble backend
  SYN/SYN-ACK assertions. No recent dropped test flows were observed.
  The Service VIP matcher has the documented upstream false negative;
  see the design README. Full policy scenarios remain due after migration,
  as explicitly approved by Dave for the dual-overlay transition.
- Temporary canary and CCNP test namespaces removed with CLI cleanup.
- Alloy initially recovered after increasing its CPU cap, then again hit
  its 256 MiB memory cap. Its cap is now 1000m CPU / 512 MiB RAM, applied
  through apply-alloy.yml. The replacement pods reached Ready 3/3 without
  restarts. verify-alloy.yml passed; a fresh Loki query found w-2 Alloy
  entries in the preceding two minutes. VictoriaMetrics reported up=1
  for all three nodes' kubelet, cAdvisor, and node-exporter targets, plus
  CoreDNS, kube-state-metrics, and Cilium Envoy targets.
- No automatic rollback after Dave's instruction to keep debugging.
  No configuration on external guests, the edge, or TrueNAS was changed.
