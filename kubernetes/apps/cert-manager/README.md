# cert-manager

Issues and renews the gateway wildcard certificates with Let's Encrypt
DNS-01 through Cloudflare. Argo CD (`homelab-platform`, manual sync) installs
the chart and [`resources/`](resources/): the `letsencrypt-staging` and
`letsencrypt-production` ClusterIssuers and two Certificates.

| Certificate | Secret | Served by |
|---|---|---|
| `tailnet-gateway/tailnet-gateway-wildcard` (`*.tail.davegallant.ca`) | `tailnet-gateway-wildcard-acme` | Cilium tailnet Gateway; Envoy reloads Secrets itself |
| `lan-gateway/lan-gateway-wildcard` (`*.davegallant.ca`) | `lan-gateway-wildcard-acme` | LAN gateway Caddy; Reloader restarts it on change |

Renewal runs 30 days before expiry (`renewBefore: 720h`) with a fresh key.
Propagation checks use `1.1.1.1`/`1.0.0.1` only: the LAN blocks Google DNS
and AdGuard answers split-horizon names.

The `cloudflare-dns-api-token` Secret comes from Vault
`cloudflare_dns_api_token`: `just run talos-cluster/gitops-secrets --tags
cert-manager-cloudflare`. The ACME account keys live only in the
`letsencrypt-*-account` Secrets; losing them just registers a new account.

## Checks

```sh
kubectl get certificate -A
kubectl get clusterissuer
nix run nixpkgs#cmctl -- status certificate -n lan-gateway lan-gateway-wildcard
```

A stuck renewal shows as `Ready=False` with a failing Challenge
(`kubectl get challenge -A`); the previous certificate keeps serving until it
expires. Force a renewal with `cmctl renew -n <ns> <name>` and verify the
served fingerprint with `openssl s_client`.
