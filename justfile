vps_host := "vps"
vps_dir := "~"

local_dir := "/Volumes/backups/pangolin"

# Show available recipes
default:
    @just --list

# Lint YAML, Ansible content and shell scripts
lint:
    yamllint -c .yamllint.yaml ansible/ kubernetes/ .github/
    cd ansible && ANSIBLE_VAULT_PASSWORD_FILE="${ANSIBLE_VAULT_PASSWORD_FILE:-$PWD/.vault_pass}" ansible-lint
    shellcheck generate-containers-table.sh scripts/*.sh

# Install the repository's pre-commit checks
install-hooks:
    git config core.hooksPath .githooks

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
    export KUBECONFIG="${KUBECONFIG:-$HOME/.local/share/homelab-talos/kubeconfig}"
    cd ansible
    ansible-playbook "playbooks/$PLAYBOOK.yml" -i inventory --vault-password-file "${ANSIBLE_VAULT_PASSWORD_FILE:-.vault_pass}" "$@"

# Edit Ansible Vault secrets
edit-secrets:
    cd ansible && ansible-vault edit group_vars/all/secrets.yaml --vault-password-file "${ANSIBLE_VAULT_PASSWORD_FILE:-.vault_pass}"

# Validate the deployed Headscale policy and managed node tags
check-headscale-policy:
    python3 scripts/check-headscale-policy.py

# Backup vps config from remote host and pull locally
backup-vps:
    #!/usr/bin/env bash
    set -euo pipefail
    pangolin_version="$(ssh {{vps_host}} 'grep -oP "fosrl/pangolin:\K[0-9]+\.[0-9]+\.[0-9]+" ~/docker-compose.yml')"
    backup_file="pangolin-${pangolin_version}-$(date +%Y%m%d).tar.gz"
    ssh {{vps_host}} bash -s -- "$backup_file" <<'REMOTE_SCRIPT'
    cd {{vps_dir}} || exit
    backup_file=$1
    docker compose stop pangolin headscale
    stop_status=$?
    if [ "$stop_status" -ne 0 ]; then
      docker compose start pangolin headscale
      exit "$stop_status"
    fi
    tar -czvf "$backup_file" config/ docker-compose.yml
    tar_status=$?
    docker compose start pangolin headscale
    start_status=$?
    if [ "$tar_status" -gt 1 ]; then
      exit "$tar_status"
    fi
    if [ "$start_status" -ne 0 ]; then
      exit "$start_status"
    fi
    REMOTE_SCRIPT
    rsync -avz --progress {{vps_host}}:{{vps_dir}}/"$backup_file" {{local_dir}}
    echo "Backup pulled locally: $backup_file"
