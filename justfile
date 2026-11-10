vps_host := "vps"
vps_dir := "~"

local_dir := "/Volumes/backups/pangolin"

# Show available recipes
default:
    @just --list

# Lint YAML, Ansible content and shell scripts
lint:
    just test
    python3 scripts/check-pod-security.py --self-test
    python3 scripts/check-rendered-pod-security.py
    yamllint -c .yamllint.yaml ansible/ kubernetes/
    python3 scripts/check-velero-backup-coverage.py
    python3 scripts/rendered_backup_coverage.py
    cd ansible && ANSIBLE_VAULT_PASSWORD_FILE="${ANSIBLE_VAULT_PASSWORD_FILE:-$PWD/.vault_pass}" ansible-lint
    shellcheck scripts/*.sh kubernetes/apps/qbittorrent/scripts/*.sh
    just lint-renovate

# Run regression tests for repository scripts
test:
    python3 -m unittest discover -s scripts/tests

# Validate the Renovate repository configuration with Renovate's own validator
lint-renovate:
    npx --yes --package renovate@41.5.0 -- renovate-config-validator renovate.json

# Install required Ansible Galaxy collections
setup:
    cd ansible && ansible-galaxy collection install -r requirements.yml

# Run an Ansible playbook (default: main); forward additional Ansible arguments
[positional-arguments]
run playbook="main" *args:
    #!/usr/bin/env bash
    set -euo pipefail
    PLAYBOOK="$1"
    shift
    cd ansible
    if [[ -f "playbooks/$PLAYBOOK.yml" ]]; then
        PLAYBOOK_PATH="playbooks/$PLAYBOOK.yml"
    elif [[ -f "playbooks/$PLAYBOOK/main.yml" ]]; then
        PLAYBOOK_PATH="playbooks/$PLAYBOOK/main.yml"
    else
        printf 'Playbook not found: %s\n' "$PLAYBOOK" >&2
        exit 1
    fi
    ansible-playbook "$PLAYBOOK_PATH" -i inventory --vault-password-file "${ANSIBLE_VAULT_PASSWORD_FILE:-.vault_pass}" "$@"

# Edit Ansible Vault secrets
edit-secrets:
    cd ansible && ansible-vault edit group_vars/all/secrets.yaml --vault-password-file "${ANSIBLE_VAULT_PASSWORD_FILE:-.vault_pass}"

# Validate the deployed Headscale policy and managed node tags
check-headscale-policy:
    python3 scripts/check-headscale-policy.py

# Build and publish the tailnet Caddy image to GitHub Container Registry
publish-tailnet-caddy:
    docker buildx build \
        --platform linux/amd64 \
        --push \
        --tag ghcr.io/davegallant/homelab-caddy-cloudflare:2.11.9-a8737d0 \
        --label org.opencontainers.image.source=https://github.com/davegallant/homelab \
        docker/tailnet-caddy


# Remove unused images older than 30 days on one explicitly selected Docker host
prune-images host:
    cd ansible && ansible "{{ host }}" -i inventory --vault-password-file "${ANSIBLE_VAULT_PASSWORD_FILE:-.vault_pass}" -m community.docker.docker_prune -a '{"images":true,"images_filters":{"dangling":false,"until":"720h"}}'

# Derive service ownership from tracked deployment definitions
service-inventory:
    python3 scripts/service_audit.py

# Report retained storage and missing Argo owners using the current cluster context
retirement-report:
    python3 scripts/service_audit.py --live
