# Local libdns Cloudflare patch

This directory is based on `github.com/libdns/cloudflare` v0.2.2. The upstream
license is retained in `LICENSE`.

The TXT-record encoder sends `libdns.TXT.Text` directly as Cloudflare API
content. The upstream encoder formats TXT RDATA as a quoted zone-file string
and then wraps it again for the API, resulting in literal quotes in the DNS
record. Caddy compares the resolved TXT value with the raw ACME challenge, so
the extra quotes make propagation checks fail.

The Caddy image build replaces the upstream module with this local copy. Keep
the patch small and review upstream updates before refreshing this snapshot.
