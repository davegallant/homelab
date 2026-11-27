# LAN gateway

A Caddy Deployment on `192.168.1.186:443` that lets home-LAN clients reach
apps already public through Pangolin without the VPS round trip. AdGuard
answers `<app>.davegallant.ca` with `192.168.1.186` only for clients in
`192.168.1.0/24`; tailnet clients query AdGuard from `100.x` and keep the
public answer, because no subnet route reaches the LAN from away.

Tailnet clients query AdGuard from `100.x` wherever they are, so they get the
`lan-gateway` tailnet node's IP instead (rule with `client=100.64.0.0/10`).
The `lan-gateway-tailnet` pod runs userspace Tailscale and forwards tailnet TCP
443 to the same Caddy Service: direct WireGuard at home, peer-to-peer away,
no VPS either way. Userspace WireGuard is slower than kernel; a remote 4K
remux may hit its ceiling.

It is separate from the tailnet gateway on purpose. Both Cilium Gateways would
share the `reserved:ingress` identity, so admitting the LAN to one would admit
it to the tailnet-only apps on `192.168.1.185`. This pod has its own identity
and accepts only `192.168.1.0/24` on TCP 8443.

## Adding an app

[`chart/values.yaml`](chart/values.yaml) is the single source: the chart,
both AdGuard instances and the coverage check all read it.
`scripts/check_lan_gateway_coverage.py` (part of `just lint`) fails when a
Newt workload is in neither `apps` nor `excluded`, when an entry has no Newt
workload, or when an app namespace is missing from the AppProject.
`just check-lan-gateway-pangolin` also compares live Pangolin hostnames.

1. Confirm the Pangolin resource has no Pangolin authentication; this path
   bypasses it.
2. Add the `apps` entry and the namespace to `homelab-lan-gateway` in
   [`project-lan-gateway.yaml`](../argocd/project-lan-gateway.yaml);
   `kubectl apply` the project.
3. Push, sync `lan-gateway` (no prune, no force), and prove the route with
   `curl --resolve <host>:443:192.168.1.186` and `:100.100.0.3`.
4. Only then publish DNS: `just run adguard-home --tags adguard_lan_gateway`
   (primary; replaces only the marked rule block) and `just run gatus`
   (secondary resolver, rendered from the same values).
5. Verify with ordinary DNS from a LAN client and a tailnet client, and that
   Pangolin still works.

## Applied by hand

[`namespace.yaml`](namespace.yaml) (also via the `pod-security` tag of
`gitops-secrets.yml`), [`lb.yaml`](lb.yaml) and [`storage.yaml`](storage.yaml): the project is
namespace-scoped only. The `lan-gateway-wildcard` TLS Secret comes from
Vault through `gitops-secrets.yml --tags lan-gateway-tls -e
lan_gateway_provision_tls=true`. The `lan-gateway-tailscale-auth` Secret
holds a single-use, one-hour Headscale pre-auth key (user `dave`), applied
once and not kept in Vault: `TS_AUTH_ONCE` means it is needed only if the
state PVC is lost, and then a fresh key is required anyway.

## Certificate

`*.davegallant.ca`, issued with Lego and Cloudflare DNS-01 into
`~/.local/share/tailnet-gateway-acme/production/state` (use resolvers
`1.1.1.1:53,1.0.0.1:53`; 8.8.8.8 is unreachable from the LAN). Renew with
30 days remaining, update `lan_gateway_tls_crt`/`lan_gateway_tls_key` in
Vault, reapply the Secret, then restart the Deployment: Caddy reads the
files only at startup.
