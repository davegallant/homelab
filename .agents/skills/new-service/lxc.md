# LXC service

1. Follow `AGENTS.md` → "Adding a New Service": add the alphabetical
   inventory entry, `ansible/playbooks/<service>/main.yml`, Compose file,
   and import in `ansible/playbooks/main.yml`. Establish that the target
   LXC exists or identify provisioning as a prerequisite.
2. Follow the canonical shared task ordering, image pinning, and firewall
   conventions. Quote Jinja values in map-form environment blocks and set
   explicit directory modes. Published Docker ports need the Docker-aware
   firewall variables; a UFW host-port allow rule alone is insufficient.
3. Follow the edge-host exceptions where applicable, including `.no-ci`
   for hosts that must run manually. Keep credentials in Ansible Vault.
4. Syntax-check the new service playbook with inventory and the Vault
   password file. Validate rendered Compose configuration without exposing
   secrets, then return to the shared integration and validation steps.

Deployment uses the Ansible service playbook. A push under `ansible/**`
can apply through CI, and the daily schedule reapplies changes; `.no-ci`
hosts require manual deployment. Push only when explicitly requested.
