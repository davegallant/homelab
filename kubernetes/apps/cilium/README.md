# Cilium CNI and network operations

## Configuration and boundaries

[values.yaml](values.yaml) and the Argo Application define intended CNI
configuration and chart version. Inspect running agents and node versions
before changes; do not infer installed state from those pins. Review workload
policy files for allowed dependencies. Endpoint policies do not isolate
host-network traffic or destinations inside userspace tunnels.

After a policy change, test both permitted and denied traffic with fresh
connections and a restarted workload. Include LAN-bound Tailscale peer traffic
in denial tests; a CIDR deny alone does not prove it is blocked.

## Primary CNI, Vault ownership, and Argo CD adoption

`cilium-primary.yml` completed the transition after every pod-network pod
verified as a Cilium endpoint. It recorded Helm retention for the three
generated TLS Secrets, materialized their existing contents from encrypted
Vault using the ansible-vault field manager, then applied steady-state values.
The steady chart references existing TLS Secrets and renders no Secrets.
The certificates were imported intact; no private key or certificate data
was printed. Certificate renewal must update Vault and rematerialize these
Secrets before expiration; Helm/Argo no longer regenerates them.

Cilium is a plain multi-source Argo CD Application, like Velero: the pinned
upstream chart plus `values.yaml` from Git `main`. Future Cilium chart and
value changes are a normal Git change to `applications/cilium.yaml` and/or
`values.yaml`, followed by a manual Argo CD sync without pruning or force.
`vars.yaml` keeps a recovery-only chart pin for `cilium.yml` and
`cilium-primary.yml` when Argo CD is unavailable; it is not the live pin.

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

Pin `envoy.xdsMode: split` explicitly. The Cilium 1.20.4 chart no longer
renders an xDS mode when this value is unset, while older chart defaults
rendered `ads`; a stale ConfigMap value can leave the agent and Envoy using
different xDS modes. `envoy.rollOutPods: true` applies ConfigMap changes to
Envoy too, with `maxUnavailable: 1` to keep a proxy available during the
DaemonSet rollout.

## WireGuard pod encryption

Cilium transparent WireGuard encryption is enabled for remote pod-to-pod
traffic with `encryption.enabled: true` and `encryption.type: wireguard`.
`encryption.nodeEncryption` remains unset, so node traffic is outside this
scope. kube-proxy replacement, VXLAN, IPAM, and policy enforcement are
unchanged.

In VXLAN mode, WireGuard peers use remote node IPs rather than pod CIDRs.
Verify peer keys, recent handshakes and increasing transfer counters. Test a
cross-node flow with paired WireGuard and underlay captures: expect encrypted
underlay traffic and no plaintext VXLAN or pod-IP packets. Use a same-node flow
as a negative control. Check resource pressure under representative workload
and backup load before calling the rollout verified.

## Hubble UI

The steady-state values enable Hubble UI on `k8s-cp-1`, with a ClusterIP
service. Apply changes with a manual Argo CD sync without pruning or force.
The chart pins both UI images by version and digest.

Access it locally:

```sh
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  kubectl -n cilium-system port-forward \
  --address 127.0.0.1 svc/hubble-ui 12000:80
```

Open <http://localhost:12000>. The UI uses Hubble Relay for flow data.

Hubble Relay CLI access uses the same localhost-only pattern:

```sh
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  kubectl -n cilium-system port-forward \
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

DNS and HTTP families require L7-parsed flows. DNS inspection is enabled by
the Jellyfin and Invidious FQDN policies, so those workloads contribute DNS
metrics while other workloads remain invisible to that metric. There are no
HTTP L7 policies yet. DNS and HTTP panels remain deferred until their
workload coverage is broad enough to be useful; their queries are:

- DNS: `sum by (rcode) (rate(hubble_dns_responses_total[5m]))`
- HTTP: `sum by (status) (rate(hubble_http_requests_total[5m]))`

The drop metric adds the source workload as a label, so the dashboard and
alerts can identify the workload that generated a denied flow. Grafana sends
a warning through the configured Gotify contact point when TCP policy drops
are observed for a workload. Its destination label uses a DNS name when Cilium
knows one, and falls back to the destination IP. The Cilium agent also exports
only dropped Hubble flows as JSON to its container logs; Alloy collects those
logs into Loki, which retains them for 31 days. The records include source and
destination workload details, IPs, ports, protocol, node, traffic direction,
and drop reason. A separate alert reports CoreDNS `SERVFAIL` responses,
including upstream resolver failures.

The four-panel dashboard is in Grafana's Homelab folder at
<https://grafana.tail.davegallant.ca/d/hubble/hubble>. The drop alert remains
focused on TCP to avoid the expected UDP discovery drops observed during the
network audit. The dashboard still shows drops across protocols by source
workload.

### Endpoint attribution

Use Hubble events to identify source/destination workloads and traffic direction.
The drop metric's `source` label identifies the source workload; the scrape
target `instance` remains the Cilium agent endpoint IP.

## Enabling Gateway API

When first enabling `gatewayAPI.enabled`, install the version-matched Gateway
API CRDs and review every rendered chart kind against the Argo project.
Cilium 1.20.3 also renders ValidatingAdmissionPolicy and its binding for the
GatewayClass. A ConfigMap-only values change rolls agents with
`rollOutCiliumPods`, but may leave the operator process unchanged. After the
new config is applied, the pinned installation instructions require an
operator rollout restart so it initializes the Gateway controller and Envoy
CRDs. Verify those CRDs and GatewayClass acceptance before calling the rollout
complete.
