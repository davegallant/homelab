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

The post-restart test of the unexpected qBittorrent peer traffic found that a
new Lidarr pod still forwards UDP to `192.168.1.152:41641`, despite the tracked
LAN egress deny. This is a real policy hole under the test criteria; no policy
was changed. See the [traffic map test evidence](traffic-map/TRAFFIC-MAP.md#post-restart-established-flow-test).

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

## WireGuard pod encryption

Cilium transparent WireGuard encryption is enabled for remote pod-to-pod
traffic with `encryption.enabled: true` and `encryption.type: wireguard`.
`encryption.nodeEncryption` remains unset, so node traffic is outside this
scope. kube-proxy replacement, VXLAN, IPAM, and policy enforcement are
unchanged. The values change is recorded in commit `37a2b282`.

The initial peer check expected remote pod CIDRs in WireGuard `allowed-ips`.
That expectation applies to native-routing mode and was incorrect for this
cluster's VXLAN tunnel mode. Cilium wraps the node-to-node VXLAN traffic in
WireGuard, so each peer correctly has the remote node IP as a `/32`. All three
agents reported `Encryption: Wireguard`, `cilium_wg0`, listen port `51871`,
two peers, matching remote `CiliumNode` public keys, and recent handshakes.
The agents were Ready and the Cilium DaemonSet was fully updated (3/3).

Cross-node TCP tests succeeded in both directions using the existing test
pods; the same-node test succeeded as the unencrypted negative control. During
a 512 KiB cross-node transfer, the `cilium_wg0` capture decoded the inner VXLAN
flow on TCP/8080 between pod IPs `10.245.2.147` and `10.245.1.110`. The paired
underlay capture observed WireGuard UDP `51871` and no plaintext VXLAN UDP
`8473` or directly visible pod-IP packets. The broad capture interval had 663
packets on `cilium_wg0`, 960 WireGuard UDP packets on the underlay, and zero
plaintext VXLAN or underlay pod-IP packets. Peer transfer counters increased
by about 589 KiB TX and 595 KiB RX during the transfer. The same-node test
flow did not appear on `cilium_wg0`. All temporary test pods and capture files
inside the Cilium agents were removed; no test workloads remained.

The w-2 baseline sampler ran from 2026-10-24 21:00:17 to 21:49:03 UTC and was
then stopped. A manual backup from the existing `navidrome-daily` schedule
provided the representative load on w-2: backup
`navidrome-daily-20261024215355` ran from 21:53:55 to 21:54:06 UTC and
completed with one PodVolumeBackup on `k8s-w-2` (`data-local`,
306,953,210 bytes). Velero reported one namespace warning because an old,
already completed Navidrome pod could not have its volume backed up; the live
pod's PodVolumeBackup completed successfully. The backup itself completed,
with no Velero or cluster errors. The scheduled nightly backup remains
unchanged.

During the backup, w-2 had about 1.50 GB available memory, 284m CPU, and
2,643 MiB memory use. The post-backup sample had about 1.49 GB available,
367m CPU, and 2,578 MiB memory use; the baseline was about 1.52–1.55 GB
available and 260–410m CPU. `MemoryPressure` remained `False`. Memory PSI had
a brief sub-0.5% ten-second average during the transfer and returned to zero
afterward; cumulative waiting and stalled time increased by about 0.078 and
0.061 seconds across the observation period. All three Cilium agents remained
Ready with zero restarts. The cluster-wide container restart total stayed at
174, with no OOM-killed containers and no running pods unready. The observation
gate passed. OCR and scan activity was waived for this closeout because the
backup was the agreed representative heavy activity.

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

## Hubble metrics and dashboard

Cilium enables the `drop`, `flow`, `dns`, and `http` metric groups. Alloy
scrapes each agent's `hubble-metrics` endpoint on TCP 9965 and remote-writes
the samples to VictoriaMetrics. The Cilium agent pods use `hostNetwork: true`,
so each target IP is its node IP. The pod-endpoint egress rule could not match
these host destinations; the approved fix added TCP 9965 to Alloy's existing
`host`/`remote-node` egress rule in `../alloy/network-policy.yaml`. The
`cilium-system` ingress rule for TCP 9965 remains as-is; namespace endpoint
policies do not govern these host-network destinations.

Alloy scrapes the three annotated Hubble service endpoints once, using
`job="prometheus.scrape.annotated_services"`. The dedicated `hubble` scrape
job was removed because it duplicated those same endpoints. VictoriaMetrics
verified three `up` series for service `hubble-metrics`; after the old
five-minute samples expired, only the annotation-driven job returned fresh
Hubble rates. At 2026-10-24 19:49 UTC, a five-minute sample was about 165
forwarded events/s and 17 drops/s; live rates vary with cluster traffic. The
dashboard filters on this job and groups by `instance`, the Cilium agent
endpoint IP.

DNS and HTTP families require L7-parsed flows. This cluster currently has no
L7 rules in its network policies and no FQDN policies, so empty DNS and HTTP
series are expected. The corresponding panels are deferred until those
policies exist; their queries to restore are:

- DNS: `sum by (rcode) (rate(hubble_dns_responses_total[5m]))`
- HTTP: `sum by (status) (rate(hubble_http_requests_total[5m]))`

The four-panel dashboard is in Grafana's Homelab folder at
<https://grafana.tail.davegallant.ca/d/hubble/hubble>. The drop alert remains
deferred pending several days of baseline observation; no alert rule was
added in this rollout.

### Hubble metric attribution follow-up

VictoriaMetrics metric labels describe the scrape target and flow class, not
flow endpoints. Neither `hubble_flows_processed_total` nor `hubble_drop_total`
includes source or destination pod, namespace, workload, or IP labels. Endpoint
attribution therefore uses Hubble flow events, not metric labels.

After the deduplicated scrape was stable, a three-minute
`hubble observe --verdict DROPPED` sample returned 826 flows, all on workers:
502 on `k8s-w-1` and 324 on `k8s-w-2`. The largest source groups were
`seerr/seerr-5bc6f4466d-t5g8x` (130 flows),
`lubelogger/lubelogger-58d8f56f67-lgtjm` (86),
`maloja/maloja-7b87fc7cf9-vx9m8` (76),
`kiwix/kiwix-d9d58c8d4-vtcnx` (74), and
`homepage/homepage-84996664c-gpj89` (58). These were UDP policy drops.

The largest destination groups were `192.168.1.52:41641` (`POLICY_DENY`,
276 flows), `204.244.250.128` (`POLICY_DENIED`, 278 flows across UDP ports
9930, 56858, 15479, 14692, 58910, and 55502), host identities
`10.245.2.92:5351` (96) and `10.245.1.169:5351` (64), and
`239.255.255.250:1900` (`POLICY_DENIED`, 56). Hubble identified the first
two IP destinations as `cidr:192.168.1.0/24`/`reserved:world` and
`reserved:world`; the 10.245 addresses were `reserved:host`. This is an
observation only. No policy was changed or widened.

A fresh `hubble observe --verdict DROPPED --since 3m` sample contained 692
flows timestamped 2026-10-24 19:59:03–20:00:06 UTC. It attributes both target
destinations to workload pods:

- `192.168.1.52:41641`: 250 UDP egress drops, `POLICY_DENY`, all on destination
  port 41641. Sources were `seerr/seerr-5bc6f4466d-t5g8x` (40),
  `sonarr/sonarr-cc778df89-44fjp` (28), `radarr/radarr-55595558c-vqdmf` (28),
  `lidarr/lidarr-7b45c964b-8xjfq` (28),
  `lubelogger/lubelogger-58d8f56f67-lgtjm` (22),
  `changedetection/changedetection-bb8d64ff7-zt2cv` (20),
  `speedtest-tracker/speedtest-tracker-5869d7b77-p5vpb` (16),
  `maloja/maloja-7b87fc7cf9-vx9m8` (14),
  `prowlarr/prowlarr-75d9d4b55-vk4m7` (14),
  `homepage/homepage-84996664c-gpj89` (14),
  `romm/romm-5d775db57f-6lsxd` (14), and
  `kiwix/kiwix-d9d58c8d4-vtcnx` (12). Dave identified `192.168.1.52` as
  Gatus; this address is not listed in the repo inventory.
- `204.244.250.128`: 218 UDP egress drops, `POLICY_DENIED`, to ports 9930
  (102), 56858 (88), 15479 (14), and 58910 (14). Sources were
  `seerr/seerr-5bc6f4466d-t5g8x` (80 total),
  `lubelogger/lubelogger-58d8f56f67-lgtjm` (44),
  `homepage/homepage-84996664c-gpj89` (42),
  `maloja/maloja-7b87fc7cf9-vx9m8` (28), and
  `kiwix/kiwix-d9d58c8d4-vtcnx` (24).

The `traffic_direction` field was `EGRESS` for every flow to both addresses.
That conflicts with the earlier task note calling the `204.244.250.128` flows
ingress; this attribution records the Hubble event field. Every captured
five-tuple to either destination repeated 12–40 times during the sample, so
these look like repeated retry-like attempts rather than one-offs; the flow
evidence does not prove application-level retry intent. No policy or Cilium
configuration was changed.

The dashboard panels select the annotation-driven job and use `instance`,
protocol, flow type, verdict, and drop reason. The namespace panels remain
removed because the available namespace label describes the scrape target,
not a flow endpoint. Source/destination pod panels remain unavailable in
metrics until Hubble emits endpoint context labels. The drop alert remains
deferred pending several days of baseline observation; no alert rule was
added.

The Talos apply playbook's bare `homelab` context expectation was stale during
the earlier run, which used `admin@homelab` after verifying the server and
node identities. The current workstation kubeconfig has only the `homelab`
context and resolves to the same expected control-plane endpoint and nodes.
Update the playbook's context check in a separate reviewed change; this run
used the default kubeconfig and made no playbook edit.

## Enabling Gateway API

When first enabling `gatewayAPI.enabled`, install the version-matched Gateway
API CRDs and review every rendered chart kind against the Argo project.
Cilium 1.20.3 also renders ValidatingAdmissionPolicy and its binding for the
GatewayClass. A ConfigMap-only values change rolls agents with
`rollOutCiliumPods`, but may leave the operator process unchanged. After the
new config is applied, the pinned installation instructions require an
operator rollout restart so it initializes the Gateway controller and Envoy
CRDs. Verify those CRDs and GatewayClass acceptance before calling the rollout
complete. See the [Gate 1 retry evidence](../../receipts/tailnet-gateway-gate-1-retry-20261026/RECEIPT.md).
