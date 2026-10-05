FROM docker.io/library/caddy:2.11.6-builder-alpine AS builder
COPY libdns-cloudflare /src/libdns-cloudflare
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare@a8737d0 \
    --replace github.com/libdns/cloudflare=/src/libdns-cloudflare

FROM docker.io/library/caddy:2.11.6-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
