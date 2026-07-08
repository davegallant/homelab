# homelab

This repo contains [ansible playbooks](./ansible/playbooks/) and docker compose files to get a number of self-hosted services up and running on my homelab.

Each host is running within a [Proxmox](https://proxmox.com) cluster in a LXC container running Ubuntu 24.04 LTS.

Why use Proxmox rather than a single host with docker compose? Mostly because Proxmox makes it trivial to both backup and migrate services between nodes using a single web interface.

## Services

<!-- DOCKER_SERVICES_START -->
| Image | Version |
|-------|---------|
| codeberg.org/forgejo/forgejo | 15.0.3 |
| data.forgejo.org/forgejo/runner | 12 |
| docker.io/aceberg/watchyourlan | v2 |
| docker.io/adguard/adguardhome | v0.107.77 |
| docker.io/archivebox/archivebox | 0.7.4 |
| docker.io/caronc/apprise | v1.5.1 |
| docker.io/chrisbenincasa/tunarr | 1.3.8 |
| docker.io/deluan/navidrome | 0.62.0 |
| docker.io/dgtlmoon/changedetection.io | 0.55.7 |
| docker.io/docker | 29.5.2-dind |
| docker.io/fosrl/newt | 1.14.0 |
| docker.io/gotify/server | 2.9.1 |
| docker.io/grafana/grafana | 13.1.0 |
| docker.io/grafana/loki | 3.7.3 |
| docker.io/henrygd/beszel | 0.18.7 |
| docker.io/itzg/minecraft-bedrock-server | 2026.7.3 |
| docker.io/jellyfin/jellyfin | 10.11.11 |
| docker.io/krateng/maloja | 3.2.4 |
| docker.io/library/redis | 8 |
| docker.io/linuxserver/lidarr | 3.1.0 |
| docker.io/linuxserver/prowlarr | 2.4.0 |
| docker.io/linuxserver/qbittorrent | 5.2.2 |
| docker.io/linuxserver/radarr | 6.2.1 |
| docker.io/linuxserver/sonarr | 4.0.19 |
| docker.io/linuxserver/speedtest-tracker | 1.14.5 |
| docker.io/mariadb | 12.2.2 |
| docker.io/miniflux/miniflux | 2.3.2 |
| docker.io/paperlessngx/paperless-ngx | 2.20.15 |
| docker.io/postgres | 18.4 |
| docker.io/rommapp/romm | 4.9.2 |
| docker.io/searxng/searxng | 2026.7.3-747cec4c2 |
| docker.io/twinproduction/gatus | v5.36.0 |
| docker.io/valkey/valkey | 9 |
| ghcr.io/advplyr/audiobookshelf | 2.35.1 |
| ghcr.io/alam00000/bentopdf | 2.8.6 |
| ghcr.io/androidseb25/igotify-notification-assist | v1.5.1.3 |
| ghcr.io/dispatcharr/dispatcharr | 0.27.2 |
| ghcr.io/flaresolverr/flaresolverr | v3.5.0 |
| ghcr.io/gethomepage/homepage | v1.13.2 |
| ghcr.io/hargata/lubelogger | v1.4.5 |
| ghcr.io/immich-app/immich-machine-learning | v3.0.1 |
| ghcr.io/immich-app/immich-server | v3.0.1 |
| ghcr.io/immich-app/postgres | 14-vectorchord0.4.3-pgvectors0.2.0 |
| ghcr.io/kiwix/kiwix-serve | 3.8.2 |
| ghcr.io/seerr-team/seerr | v3.3.0 |
| ghcr.io/umami-software/umami | 3.2.0 |
| quay.io/invidious/invidious | 2026.06.30-77ad416 |
| quay.io/invidious/invidious-companion | master-6c76cab |
<!-- DOCKER_SERVICES_END -->

## Networking

All hosts have tailscale installed on them, with [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh). In some cases, [tailscale serve](https://tailscale.com/kb/1242/tailscale-serve) is used to expose services with [Let's Encrypt](https://letsencrypt.org/) certificates.

Tailscale ACLs are used to tag and restrict nodes from accessing eachother.

## Logging

Each host runs an instance of [Alloy](https://github.com/grafana/alloy) managed by systemd allowing for all journald and docker logs to be collected, labelled and sent to Grafana Loki.

## Maintenance

[ProxMenux](https://github.com/MacRimi/ProxMenux) is used to run update scripts and monitor key vitals of running proxmox nodes.

Renovate is used to update dependencies and [pin digests](https://docs.renovatebot.com/presets-docker/#dockerpindigests).
