---
name: new-service
description: "Use when adding a new self-hosted service to this homelab (a new ansible/playbooks/<service> directory). Ensures the service is wired into homepage and gatus in addition to the base Ansible scaffolding, so nothing new goes unmonitored or missing from the dashboard."
---

Add a new service to this homelab so it shows up in **both** homepage
(the dashboard) and gatus (uptime monitoring), not just its own playbook.
This repo shares URL variables between the two -- see
`ansible/playbooks/gatus/config/config.yaml` and
`ansible/playbooks/homepage/config/services.yaml` for the existing pattern.

## Steps

1. **Scaffold the service playbook** following `AGENTS.md` → "Adding a New
   Service": inventory entry, `main.yml`, `docker-compose.yml`, import line
   in `ansible/playbooks/main.yml`.

2. **Add (or reuse) a shared URL secret.**
   - Decrypt the vault to a scratch file, edit, re-encrypt -- do not try to
     hand-edit the encrypted file:
     ```sh
     cd ansible
     ansible-vault view group_vars/all/secrets.yaml \
       --vault-password-file .vault_pass > /tmp/secrets_plain.yaml
     # edit /tmp/secrets_plain.yaml
     ansible-vault encrypt /tmp/secrets_plain.yaml \
       --vault-password-file .vault_pass \
       --output group_vars/all/secrets.yaml
     rm /tmp/secrets_plain.yaml
     ```
   - Add a bare `<service>_url: "https://<service>.snake-cloud.ts.net"` (or
     the public `davegallant.ca` hostname, matching whatever the service's
     own docker-compose/Tailscale config uses). No `homepage_` prefix --
     this var is shared, not homepage-only.
   - If the var already exists (reused from another playbook, e.g.
     `forgejo_root_url`), don't create a duplicate -- reference the
     existing one from both homepage and gatus instead.
   - Any service-specific credential the *dashboard* needs (API key,
     username/password for a homepage widget) stays homepage-only and keeps
     the `homepage_` prefix, since gatus doesn't need it.

3. **Add the service to homepage**
   (`ansible/playbooks/homepage/config/services.yaml` and
   `ansible/playbooks/homepage/docker-compose.yml`):
   - In `docker-compose.yml`, add
     `- "HOMEPAGE_VAR_<SERVICE>_URL={{ <service>_url }}"` to the
     `environment:` list (keep it alphabetically near related entries, not
     necessarily sorted -- match the existing loose grouping).
   - In `services.yaml`, add an entry under the appropriate group
     (`Stats` for services with a homepage widget type, `Quick Links` for a
     plain link) using
     `{% raw %}{{HOMEPAGE_VAR_<SERVICE>_URL}}{% endraw %}` for `href`, plus
     an `icon:` and `description:`.

4. **Add the service to gatus**
   (`ansible/playbooks/gatus/config/config.yaml`):
   - Append an endpoint entry:
     ```yaml
     - name: <service>
       url: "{{ <service>_url }}"
       <<: *defaults
     ```
   - If the service needs a specific health path (e.g. `/health`,
     `/admin/login`), append it to the URL var inline --
     `url: "{{ <service>_url }}health"` -- matching how `prowlarr` and
     `speedtest-tracker` do it (mind trailing slashes on the var value).
   - If the service uses a self-signed cert or otherwise fails TLS
     verification, override the client block on that endpoint only
     (see the `truenas` entry for the pattern) -- never loosen
     `endpoint-defaults`.

5. **Verify by rendering, not by guessing.** Ansible vars/templates fail
   silently wrong if a var name is off. Render both templates against the
   real vault and inspect the output:
   ```sh
   cd ansible
   cat > /tmp/render_check.yml <<'EOF'
   ---
   - name: render check
     hosts: localhost
     connection: local
     gather_facts: false
     vars_files:
       - group_vars/all/secrets.yaml
     tasks:
       - ansible.builtin.template:
           src: playbooks/gatus/config/config.yaml
           dest: /tmp/rendered_gatus_config.yaml
       - ansible.builtin.template:
           src: playbooks/homepage/docker-compose.yml
           dest: /tmp/rendered_homepage_compose.yaml
   EOF
   ansible-playbook /tmp/render_check.yml --vault-password-file .vault_pass
   python3 -c "import yaml; yaml.safe_load(open('/tmp/rendered_gatus_config.yaml'))"
   grep "<SERVICE>" /tmp/rendered_homepage_compose.yaml /tmp/rendered_gatus_config.yaml
   rm /tmp/render_check.yml /tmp/rendered_gatus_config.yaml /tmp/rendered_homepage_compose.yaml
   ```
   Confirm both files show the real resolved URL, not a literal `{{ }}` or
   an empty string (which means the var name is wrong or undefined).
   Then run `ansible-playbook playbooks/gatus/main.yml --syntax-check
   --vault-password-file .vault_pass` and the same for `homepage/main.yml`.

6. **Sandbox note.** If `ansible-vault`/`ansible-playbook` fail with
   `DEFAULT_LOCAL_TMP` permission errors, set
   `ANSIBLE_LOCAL_TEMP`/`ANSIBLE_REMOTE_TEMP` to a writable scratch dir
   before invoking them.
