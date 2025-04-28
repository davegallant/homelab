# homelab

This repo contains [ansible playbooks](./ansible/playbooks/) and docker compose files to get a number of self-hosted services up and running on my homelab.

![Overview](https://github.com/user-attachments/assets/1b86c4b5-026a-494b-acf9-1f936daa1d27)

Each host is running on [proxmox](https://proxmox.com) in a LXC container running Ubuntu 24.04 LTS.

Why use proxmox rather than a single host with docker compose? Mostly because proxmox makes it trivial to both backup and migrate services between proxmox nodes using a single web interface. A similar setup could also be achieved using k8s but I wanted to avoid the complexity for now.

## Networking

Most hosts have tailscale installed on them, with [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh) enabled using either [serve](https://tailscale.com/kb/1242/tailscale-serve) or [funnel](https://tailscale.com/kb/1311/tailscale-funnel) to expose services with [Let's Encrypt](https://letsencrypt.org/) certificates.

## Maintenance

I've cloned [Proxmox VE Helper-Scripts](https://github.com/community-scripts/ProxmoxVE) and run a few of the scripts to cleanup and update LXC containers.
