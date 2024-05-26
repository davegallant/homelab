# homelab

This repo contains ansible playbooks and docker compose files to get a number of self-hosted services up and running on my homelab.

## proxmox

> ℹ️ Why use proxmox rather than a single host with docker compose or k8s? Mostly because I prefer the organization of services into their own hosts. It's also very trivial to both backup and migrate services between proxmox nodes.

Each host is running on proxmox within a LXC container. Hosts are running on either Debian or Ubuntu-based CT templates.

[Proxmox VE Helper-Scripts](https://github.com/tteck/Proxmox) are used to cleanup and update containers within proxmox.

### Templates

More recent services are running on Ubuntu due to an issue with dhclient continually writing to /etc/resolv.conf breaking TailScale's MagicDNS. I plan to migrate all hosts to Ubuntu eventually.

## Tailscale

Most hosts have tailscale installed on them with tailscale ssh enabled so that keys can be managed through tailscale.
