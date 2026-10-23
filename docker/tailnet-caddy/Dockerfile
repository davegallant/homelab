FROM docker.io/library/caddy:2.11.7-builder-alpine@sha256:ef9b65adf9a224770c6d5f6d1ae1bf99bc3caaa78d8c4bae3ea949ee6984f301 AS builder
COPY libdns-cloudflare /src/libdns-cloudflare
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare@a8737d0 \
    --replace github.com/libdns/cloudflare=/src/libdns-cloudflare

FROM docker.io/library/caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
