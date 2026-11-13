FROM docker.io/library/caddy:2.11.9-builder-alpine@sha256:646fee578e680989ca5c7fd1ce6f1de574d19fd71ef2221810cc0510a9f40c86 AS builder
COPY libdns-cloudflare /src/libdns-cloudflare
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare@a8737d0 \
    --replace github.com/libdns/cloudflare=/src/libdns-cloudflare

FROM docker.io/library/caddy:2.11.9-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
