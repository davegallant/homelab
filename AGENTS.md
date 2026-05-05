# AGENTS.md

Docker-based homelab managed with Ansible. Provisions self-hosted services, each
in a Proxmox LXC container on Ubuntu 24.04 LTS. Each service gets Docker installed
via Ansible, then a `docker-compose.yml` is deployed and started. Networking is via
Tailscale. Logging is centralized via Grafana Alloy to Loki.

## Build / Run Commands

All commands are run from the `ansible/` directory using [just](https://github.com/casey/just):

```sh
just setup                              # Install Ansible Galaxy collections
just run "--limit grafana"              # Run all playbooks limited to one host
# Run a single service playbook directly:
ansible-playbook playbooks/grafana/main.yml -i inventory --vault-password-file .vault_pass
```

### CI/CD

- **On push to `main`**: all 38 playbooks run in a GitHub Actions matrix
- **Manual dispatch**: run a single playbook by name via `run-single-playbook.yml`
- **On compose file changes**: `update-containers-table.yml` regenerates the README table

There are no unit tests or integration tests. CI runs the actual Ansible playbooks
against real infrastructure. The vault password is injected from `secrets.ANSIBLE_VAULT_PASSWORD`.

## Ansible Playbook Conventions

### Playbook structure (canonical form)

Every service playbook follows this exact pattern:

```yaml
---
- name: Install <service-name>
  hosts: <service-name>
  tasks:
    - ansible.builtin.include_tasks:
        file: ../../tasks/install-docker.yml

    - ansible.builtin.include_tasks:
        file: ../../tasks/install-common-packages.yml

    - ansible.builtin.include_tasks:
        file: ../../tasks/install-alloy.yml

    - name: Copy docker-compose.yml
      ansible.builtin.template:
        src: docker-compose.yml
        dest: "~/docker-compose.yml"
        mode: "0640"

    - name: Enable UFW
      community.general.ufw:
        state: enabled
        policy: deny

    - ansible.builtin.include_tasks:
        file: ../../tasks/docker-pull.yml
```

### Style rules

- **Indentation**: 2 spaces, always
- **Document start**: playbook `main.yml` files begin with `---`; shared task files and
  docker-compose files do not
- **Play naming**: `Install <lowercase-service-name>` (sentence case, service name lowercase)
- **Task naming**: sentence case, action-oriented (e.g., `Copy docker-compose.yml`,
  `Enable UFW`, `Allow bedrock port`)
- **Module names**: always use Fully Qualified Collection Names (FQCNs):
  `ansible.builtin.template`, `community.general.ufw`, `community.docker.docker_compose_v2`
- **Booleans**: use `true`/`false`, never `yes`/`no`
- **File mode**: always a quoted string: `"0640"`, `"0644"`, `"0755"`
- **Variable references**: `{{ var }}` with spaces inside braces
- **Privilege escalation**: not specified (hosts are accessed as root via Tailscale SSH)
- **Task directive order**: `name:` first, then module with parameters, then conditionals
- **Hosts value**: must match the playbook directory name and the inventory hostname
- **Use `ansible.builtin.template`** for copying compose files (even if no variables),
  not `ansible.builtin.copy`

### Task ordering within a playbook

1. Include `install-docker.yml`
2. Include `install-common-packages.yml`
3. Include `install-alloy.yml`
4. Copy compose file(s) and any extra config files
5. UFW allow rules for specific ports (if needed)
6. Enable UFW with deny-all policy
7. Include `docker-pull.yml` (always last)

## Docker Compose Conventions

- **No `version:` key** (it is deprecated)
- **Image registry**: always fully qualified -- `docker.io/`, `ghcr.io/`, `quay.io/`
  - Official images: `docker.io/library/postgres:15-alpine`
  - Third-party: `docker.io/grafana/grafana:12.4.1`
- **Image tags**: always pinned to a specific version, never `latest`
- **`container_name`**: always specified explicitly
- **`restart`**: `always` for primary services, `unless-stopped` for sidecars/helpers
- **Volumes**: short string syntax (`./data:/data`), read-only with `:ro` suffix
- **Environment variables**: prefer list form (`- KEY=value`); map form (`KEY: value`)
  is acceptable but less common
- **Networks**: named networks matching the service name, used when a Newt reverse proxy
  sidecar is present
- **Newt sidecar pattern** (for Pangolin reverse proxy tunneling):
  ```yaml
  newt:
    image: docker.io/fosrl/newt:<version>
    container_name: newt-<service-name>
    restart: unless-stopped
    networks:
      - <service-name>
    environment:
      - PANGOLIN_ENDPOINT={{ pangolin_endpoint }}
      - NEWT_ID={{ service_newt_id }}
      - NEWT_SECRET={{ service_newt_secret }}
  ```

## Bash Script Conventions

- Shebang: `#!/usr/bin/env bash`; strict mode: `set -euo pipefail`
- Variables: `UPPER_SNAKE_CASE`, always double-quoted (`"$VAR"`)
- Temp file cleanup: use `trap ... EXIT`

## CI / GitHub Actions Conventions

- Workflow and step names: sentence case; action versions: major-version pinning (`@v6`)
- Runner: `ubuntu-latest`; multi-line shell: `run: |` (literal block scalar)
- Automated commit messages: conventional commits format (`chore: update containers table`)

## Dependency Management

- **Renovate** auto-merges minor/patch/pin/digest updates on weekends (`renovate.json`)
- Container image versions are pinned in each `docker-compose.yml`
- Ansible Galaxy collections: `ansible.posix`, `community.docker`, `community.general`

## Adding a New Service

1. Add host to `ansible/inventory` under `[homelab]` (alphabetical order)
2. Create `ansible/playbooks/<service>/main.yml` following the canonical structure above
3. Create `ansible/playbooks/<service>/docker-compose.yml` following compose conventions
4. Add an import line in `ansible/playbooks/main.yml`
5. If using secrets, reference via `{{ variable }}` and define in `group_vars/all/secrets.yaml`
