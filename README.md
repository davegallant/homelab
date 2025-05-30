# homelab

This repo contains [ansible playbooks](./ansible/playbooks/) and docker compose files to get a number of self-hosted services up and running on my homelab.

![Overview](https://github.com/user-attachments/assets/9bcf4b52-f74f-43b9-947e-2059336ee146)

Each host is running within a [Proxmox](https://proxmox.com) cluster in a LXC container running Ubuntu 24.04 LTS.

Why use Proxmox rather than a single host with docker compose? Mostly because Proxmox makes it trivial to both backup and migrate services between nodes using a single web interface. A similar setup could also be achieved using k8s but I wanted to avoid the complexity for now.

## Networking

All hosts have tailscale installed on them, with [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh) enabled using either [serve](https://tailscale.com/kb/1242/tailscale-serve) or [funnel](https://tailscale.com/kb/1311/tailscale-funnel) to expose services with [Let's Encrypt](https://letsencrypt.org/) certificates.

## Maintenance

I've cloned [Proxmox VE Helper-Scripts](https://github.com/community-scripts/ProxmoxVE) and run a few of the scripts to cleanup and update LXC containers.
