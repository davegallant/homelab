# Central Cilium Gateway — tailnet-only, test-first design

Goal: replace per-app Tailscale + Caddy sidecars with ONE central
entry point. Apps become app container + ClusterIP Service +
HTTPRoute. No per-app Tailscale, Caddy, Cloudflare cert, or
tailscale-state/caddy-state PVCs after migration.

Status: CODE ONLY, NOT SYNCED, NOT PROVEN. Gate 0 questions
below are unproven and must be settled doc-first before any sync.
Do NOT apply these manifests as-is.

## Intended flow (after Gate 0 proves it)

Tailnet device -> Tailscale fronting pod (100.x, preauth pattern)
  -> Cilium Gateway listener 443, HTTPS, *.tail.davegallant.ca
  -> HTTPRoute by hostname -> app ClusterIP Service -> app pod

## What is in this folder

- `namespace.yaml` — tailnet-gateway namespace.
- `gateway.yaml` — Gateway, GatewayClassName cilium, listener
  https 443, hostname *.tail.davegallant.ca, TLS Terminate with
  Secret tailnet-gateway-wildcard (NOT in Git, see Cert below).
- `httproute-changedetection-test.yaml` — HTTPRoute in namespace
  changedetection, hostname changedetection-gw.tail.davegallant.ca,
  backend Service changedetection:5000 (the app's existing
  ClusterIP Service, NOT its Caddy port). Sidecar stays live.
- `referencegrant-gateway.yaml` — comment-only correction: no grant is
  needed. The Gateway listener uses `allowedRoutes` restricted to the
  changedetection namespace. The backend Service and TLS Secret each
  live in the same namespace as their referring resource.
- `fronting-pod.yaml` — TEMPLATE ONLY, GATE-0-OPEN. A Tailscale
  sidecar pod with a placeholder TCPForward destination. Gate 0
  must prove the real destination and correct this file, or
  replace this fronting mechanism entirely. Do NOT apply it
  with the placeholder.
- Argo Application: `../argocd/applications/tailnet-gateway.yaml`
  (project, sync policy, and source path to be corrected at
  Gate 0 — see Project below).

## Gate 0 open questions (unproven, doc-first, halt if unproven)

1. Cilium Gateway API is NOT enabled in live values today.
   `kubernetes/apps/cilium/values.yaml` (2026-10-26) has
   kubeProxyReplacement, egressGateway, BPF masquerade, but
   NO gatewayAPI, NO l2announcer, NO LB-IPAM pool. Gate 0 must
   read Cilium 1.20.3 docs and record the exact values change
   needed (gatewayAPI.enabled, l2announcer, LB pool / IPAM,
   GatewayClass, Envoy data-plane pods if any), the rollout
   risk to the CNI, and whether a Cilium values change needs
   Dave's separate go. Do NOT assume GatewayClass cilium
   exists until `kubectl get gatewayclass` proves it.
2. Tailnet fronting mechanism is UNPROVEN. A Tailscale
   userspace sidecar currently forwards TCP 443 to
   127.0.0.1:8443 in-pod. Forwarding to a Gateway Service
   ClusterIP / LB IP from a pod is a different destination:
   Gate 0 must prove, from Tailscale Serve docs, whether
   TCPForward accepts a Service DNS name or a stable IP, how
   that IP is obtained (Gateway Service ClusterIP is dynamic,
   LB IP needs an IPAM pool and a DHCP-reserved LAN address
   confirmed against OPNsense — do NOT guess an IP), or
   whether the fronting mechanism must instead be a subnet
   router advertising the Gateway LB IP, or a central Caddy
   pod (proven pattern, once, not per app). If none is
   proven, Gate 0 FAILS and the run stops — do NOT invent
   a fronting destination.
3. Wildcard TLS cert does NOT exist yet. There is no
   cert-manager in the cluster, and per-app Caddy certs live
   in caddy-state PVCs, not in Secrets a Gateway can use.
   Gate 0 must produce a cert plan: how *.tail.davegallant.ca
   is issued via Cloudflare DNS-01, stored in Vault, applied
   as Secret tailnet-gateway-wildcard, and renewed — and get
   Dave's go before any issuance (Let's Encrypt rate limits,
   Cloudflare API use). No real cert, no Gate 2 HTTPS pass.
   HTTP-only is NOT a pass.
4. Project permissions: Gate 0 must verify homelab-platform
   (or homelab, if the Gateway lives there) permits the
   Gateway API kinds (Gateway, HTTPRoute, ReferenceGrant),
   the tailnet-gateway destination, and any Cilium LB pool
   kinds. Record the exact project change needed if missing;
   do NOT edit the project unasked.

## Fallback if Gate 0 fails on Gateway API fronting/TLS

Central Caddy pod, once, not per app: one Deployment with
Tailscale + Caddy, Caddyfile routing by hostname to app
ClusterIP Services, one wildcard cert issued by that Caddy
via Cloudflare DNS-01. This is the proven sidecar pattern,
centralised, with NO Gateway API, NO Cilium values change,
NO LB-IPAM. It still deletes per-app sidecars. It is a
separate design decision for Dave, not a silent pivot.

## Migration order (after a Gateway test passes)

1. Gateway + fronting + test route only, changedetection
   sidecar stays live. Verify HTTPS on
   changedetection-gw.tail.davegallant.ca from a tailnet
   device, app responding.
2. STOP and report. Only then, per app, on Dave's go:
   switch real hostname to Gateway, remove per-app Tailscale/Caddy
   resources where the current manifests declare them, update its NetworkPolicy to allow
   gateway -> app port (current policies allow same-
   namespace ingress only, which Gateway traffic is not).
3. Order: changedetection, then Prowlarr, then k8s-readonly.

Homepage's widget proxy is separate from inbound Gateway routing. Verify real
widget/API and WebSocket calls when changing that path.

## Out of scope, always

- Public services: Audiobookshelf stays public, Forgejo
  stays via Newt. This Gateway is tailnet-only, no public
  IP, no Cloudflare tunnel, no Newt resource.
- Bedrock/UDP: L7 Gateway does not help UDP. Bedrock stays
  on its LXC.
- No Headscale ACL change, OPNsense change, PVC resize,
  image bump, commit, or push unless Dave says so in
  the moment. No secret values in Git, ever.
