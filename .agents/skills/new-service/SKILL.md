---
name: new-service
description: "Use when adding a self-hosted service to this homelab, either Docker Compose on a Proxmox LXC or a Kubernetes application managed by Argo CD."
---

# Add a service

Complete the selected platform scaffolding, Homepage entry, and Gatus
monitoring together. Paths below are relative to the repository root.

## Choose the deployment target

Use the target specified in the request or established in the conversation.
If it is unclear, ask whether the service should run on LXC or Kubernetes
before creating platform files.

| Target | Required reference |
| --- | --- |
| LXC with Docker Compose | [LXC service](lxc.md) |
| Kubernetes with Argo CD | [Argo CD application](argocd.md) |

Read and follow the selected reference, then complete the shared steps below.
For a migration, also define data transfer, verification, identity handoff,
and rollback before changing the running service.

## Shared integration

1. **Add or reuse the shared URL variable.** Check
   `ansible/group_vars/all/vars.yaml` and the Vault-backed
   `ansible/group_vars/all/secrets.yaml` for an existing variable first.
   Use a shared `<service>_url` name without a `homepage_` prefix, matching
   the service's actual tailnet or public hostname. Follow the existing
   variable's storage convention; new non-secret shared values belong in
   `vars.yaml`. Edit secrets with `just edit-secrets` from `ansible/`;
   keep plaintext secrets out of command output and unprotected files.
   Homepage widget credentials retain the `homepage_` prefix.

2. **Add the service to Homepage on Talos.** Read
   `kubernetes/apps/homepage/README.md` before editing its configuration.
   The former Homepage LXC is retired.
   - Add `HOMEPAGE_VAR_<SERVICE>_URL: {{ <service>_url | to_json }}` under
     the existing environment mapping in
     `kubernetes/apps/homepage/values.ansible.yaml.j2`.
   - Add an entry to
     `kubernetes/apps/homepage/config/services.yaml` under the appropriate
     existing group, with an icon and description. Use
     `"{% raw %}{{HOMEPAGE_VAR_<SERVICE>_URL}}{% endraw %}"` for `href`.
     Follow a comparable entry for widget configuration and credentials.
   - Homepage configuration and Secrets are rendered by
     `ansible/playbooks/talos-cluster/gitops-secrets.yml`. Follow the
     Homepage runbook for applying them and restarting the Deployment to
     refresh subPath mounts; changes to the tracked checksum require an
     approved Argo CD sync.

3. **Add Gatus monitoring** in
   `ansible/playbooks/gatus/config/config.yaml`:
   ```yaml
   - name: <service>
     url: "{{ <service>_url }}"
     <<: *defaults
   ```
   Choose a useful health path and account for the URL variable's trailing
   slash. If TLS verification needs an exception, scope it to this endpoint
   using the existing TrueNAS entry as a reference.

## Validation and delivery

Run the selected platform's validation and `just lint` from the repo root,
using the protected Vault password helper required by `AGENTS.md`.
Render the Gatus template and Homepage Ansible values bridge with the real
inventory and Vault variables. Parse the rendered YAML and confirm the new
URL resolves in both consumers. Homepage's intentional runtime
`{{HOMEPAGE_VAR_...}}` placeholders must survive in services YAML.
Keep secret-bearing renders in protected temporary files with cleanup;
report results without credentials. Syntax-check the Gatus playbook with
the Vault password file.

Work on local `main`; push only on explicit request. Report changed files,
validation results, and remaining deployment steps. Apply live changes only
within the authorized deployment scope. Homepage external resources and its
Deployment restart are separate from the new service's deployment.
