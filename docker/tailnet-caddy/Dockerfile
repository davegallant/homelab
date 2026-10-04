FROM docker.io/library/caddy:2.11.6-builder-alpine AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare@a8737d0

FROM docker.io/library/caddy:2.11.6-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
