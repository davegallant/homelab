# LAN gateway

A Caddy Deployment on `192.168.1.186:443` that lets home-LAN clients reach
apps already public through Pangolin without the VPS round trip. AdGuard
answers `<app>.davegallant.ca` with `192.168.1.186` only for clients in
`192.168.1.0/24`; tailnet clients query AdGuard from `100.x` and keep the
public answer, because no subnet route reaches the LAN from away.

It is separate from the tailnet gateway on purpose. Both Cilium Gateways would
share the `reserved:ingress` identity, so admitting the LAN to one would admit
it to the tailnet-only apps on `192.168.1.185`. This pod has its own identity
and accepts only `192.168.1.0/24` on TCP 8443.

## Adding an app

1. Confirm the Pangolin resource has no Pangolin authentication; this path
   bypasses it.
2. Add an entry to [`chart/values.yaml`](chart/values.yaml) and the app
   namespace to `homelab-lan-gateway` in
   [`project-lan-gateway.yaml`](../argocd/project-lan-gateway.yaml).
3. Sync `lan-gateway` (no prune, no force) and check the backend policy.
4. Add the AdGuard rule
   `||<app>.davegallant.ca^$dnsrewrite=192.168.1.186,client=192.168.1.0/24`.
5. Verify from a LAN client without `--resolve`, and that Pangolin still works.

## Applied by hand

[`namespace.yaml`](namespace.yaml) (also via the `pod-security` tag of
`gitops-secrets.yml`) and [`lb.yaml`](lb.yaml): the project is
namespace-scoped only. The `lan-gateway-wildcard` TLS Secret comes from
Vault through `gitops-secrets.yml --tags lan-gateway-tls -e
lan_gateway_provision_tls=true`.

## Certificate

`*.davegallant.ca`, issued with Lego and Cloudflare DNS-01 into
`~/.local/share/tailnet-gateway-acme/production/state` (use resolvers
`1.1.1.1:53,1.0.0.1:53`; 8.8.8.8 is unreachable from the LAN). Renew with
30 days remaining, update `lan_gateway_tls_crt`/`lan_gateway_tls_key` in
Vault, reapply the Secret, then restart the Deployment: Caddy reads the
files only at startup.
