# homelab

This repo contains ansible playbooks and docker compose files to get a number of self-hosted services up and running on my homelab.

## proxmox

Each host is running on proxmox in a LXC container. Most containers are based on Ubuntu 22.02.

[Proxmox VE Helper-Scripts](https://github.com/coelacant1/ProxmoxScripts.git) are used to cleanup and update containers within proxmox.

> ℹ️ Why use proxmox rather than a single host with docker compose? Mostly because proxmox makes it trivial to both backup and migrate services between proxmox nodes using a single web interface. A similar setup could also be achieved using k8s but I wanted to avoid the complexity for now.

### Templates

More recent services are running on Ubuntu due to an issue with dhclient continually writing to /etc/resolv.conf breaking TailScale's MagicDNS on debian bookworm.

## Tailscale

Most hosts have tailscale installed on them with tailscale ssh enabled so that any keys can be managed through tailscale.
