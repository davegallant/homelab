# homelab

This repo contains [ansible playbooks](./ansible/playbooks/) and docker compose files to get a number of self-hosted services up and running on my homelab.

Each host is running within a [Proxmox](https://proxmox.com) cluster in a LXC container running Ubuntu 24.04 LTS.

Why use Proxmox rather than a single host with docker compose? Mostly because Proxmox makes it trivial to both backup and migrate services between nodes using a single web interface.

## Services

<!-- DOCKER_SERVICES_START -->
| Image | Version |
|-------|---------|
| docker.io/aceberg/watchyourlan | v2 |
| docker.io/archivebox/archivebox | 0.7.3 |
| docker.io/caronc/apprise | v1.3.3 |
| docker.io/chrisbenincasa/tunarr | 1.2.10 |
| docker.io/deluan/navidrome | 0.61.0 |
| docker.io/dgtlmoon/changedetection.io | 0.54.8 |
| docker.io/fosrl/newt | 1.11.0 |
| docker.io/gitea/gitea | 1.25.5 |
| docker.io/gotify/server | 2.9.1 |
| docker.io/grafana/grafana | 12.4.2 |
| docker.io/grafana/loki | 3.7.1 |
| docker.io/henrygd/beszel | 0.18.6 |
| docker.io/itzg/minecraft-bedrock-server | 2026.4.0 |
| docker.io/jellyfin/jellyfin | 10.11.7 |
| docker.io/krateng/maloja | 3.2.4 |
| docker.io/library/postgres | 14 |
| docker.io/library/postgres | 15-alpine |
| docker.io/library/redis | 8 |
| docker.io/linuxserver/calibre-web | 0.6.26 |
| docker.io/linuxserver/lidarr | 3.1.0 |
| docker.io/linuxserver/prowlarr | 2.3.0 |
| docker.io/linuxserver/qbittorrent | 5.1.4 |
| docker.io/linuxserver/radarr | 6.1.1 |
| docker.io/linuxserver/sonarr | 4.0.17 |
| docker.io/linuxserver/speedtest-tracker | 1.13.12 |
| docker.io/mariadb | 12.2.2 |
| docker.io/miniflux/miniflux | 2.2.18 |
| docker.io/paperlessngx/paperless-ngx | 2.20.13 |
| docker.io/postgres | 15 |
| docker.io/postgres | 15-alpine |
| docker.io/postgres | 15.17 |
| docker.io/rommapp/romm | 4.8.1 |
| docker.io/searxng/searxng | 2026.2.19-17544140f |
| docker.io/tensorchord/pgvecto-rs | pg14-v0.2.0@sha256 |
| docker.io/twinproduction/gatus | v5.35.0 |
| docker.io/valkey/valkey | 9 |
| docker.io/vaultwarden/server | 1.35.4 |
| ghcr.io/advplyr/audiobookshelf | 2.33.1 |
| ghcr.io/alam00000/bentopdf | 2.8.1 |
| ghcr.io/androidseb25/igotify-notification-assist | v1.5.1.3 |
| ghcr.io/autobrr/qui | v1.15.0 |
| ghcr.io/davegallant/rfd-fyi | 0.2.0 |
| ghcr.io/dispatcharr/dispatcharr | 0.22.0 |
| ghcr.io/gethomepage/homepage | v1.12.3 |
| ghcr.io/hargata/lubelogger | v1.4.5 |
| ghcr.io/immich-app/immich-machine-learning | v2.6.3 |
| ghcr.io/immich-app/immich-server | v2.6.3 |
| ghcr.io/kiwix/kiwix-serve | 3.8.2 |
| ghcr.io/seerr-team/seerr | v3.1.0 |
| ghcr.io/seriousm4x/upsnap | 5.3.2 |
| ghcr.io/umami-software/umami | 3.0.3 |
| quay.io/invidious/invidious | 2026.02.16-e7f8b15 |
| quay.io/invidious/invidious-companion | master-6c76cab |
| quay.io/redlib/redlib | sha-ba98178 |
<!-- DOCKER_SERVICES_END -->

## Networking

All hosts have tailscale installed on them, with [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh) enabled using either [serve](https://tailscale.com/kb/1242/tailscale-serve) or [funnel](https://tailscale.com/kb/1311/tailscale-funnel) to expose services with [Let's Encrypt](https://letsencrypt.org/) certificates.

## Logging

Each host runs an instance of [Alloy](https://github.com/grafana/alloy) managed by systemd allowing for all journald and docker logs to be collected, labelled and sent to Grafana Loki.

## Maintenance

I've cloned [Proxmox VE Helper-Scripts](https://github.com/community-scripts/ProxmoxVE) and run a few of the scripts to cleanup and update LXC containers.
