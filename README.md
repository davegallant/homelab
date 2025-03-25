# homelab

This repo contains [ansible playbooks](./ansible/playbooks/) and docker compose files to get a number of self-hosted services up and running on my homelab.

Each host is running on [proxmox](https://proxmox.com) in a LXC container and is running Ubuntu 22.04 LTS. Due to a [conflict with MagicDNS and DHCP](https://github.com/tailscale/tailscale/issues/12676) (dhclient continually writing to /etc/resolv.conf breaking TailScale's MagicDNS), there is no plan on upgrading to Ubuntu 24 (and beyond) until this is resolved.

[Proxmox VE Helper-Scripts](https://github.com/community-scripts/ProxmoxVE) are used to cleanup and update containers within proxmox.

> Why use proxmox rather than a single host with docker compose?
>
> Mostly due to the fact that proxmox makes it trivial to both backup and migrate services between proxmox nodes using a single web interface. A similar setup could also be achieved using k8s but I wanted to avoid the complexity for now.

Most hosts have tailscale installed on them, with [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh) enabled using either [serve](https://tailscale.com/kb/1242/tailscale-serve) or [funnel](https://tailscale.com/kb/1311/tailscale-funnel) to expose services with [Let's Encrypt](https://letsencrypt.org/) certificates.
