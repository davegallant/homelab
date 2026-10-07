FROM docker.io/library/caddy:2.11.7-builder-alpine@sha256:80331d37e7d4d230f186f2707079e279f32552924f101ee659e8cae9f9877c26 AS builder
COPY libdns-cloudflare /src/libdns-cloudflare
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare@a8737d0 \
    --replace github.com/libdns/cloudflare=/src/libdns-cloudflare

FROM docker.io/library/caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
