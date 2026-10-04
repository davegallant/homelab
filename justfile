pangolin_host := "pangolin"
pangolin_dir := "~"

local_dir := "/Volumes/backups/pangolin"

# Show available recipes
default:
    @just --list

# Lint YAML, Ansible content and shell scripts
lint:
    yamllint -c .yamllint.yaml ansible/ .forgejo/ .github/
    cd ansible && ansible-lint
    shellcheck generate-containers-table.sh scripts/*.sh

# Backup pangolin config from remote host and pull locally
backup-pangolin:
    #!/usr/bin/env bash
    set -euo pipefail
    pangolin_version="$(ssh {{pangolin_host}} 'grep -oP "fosrl/pangolin:\K[0-9]+\.[0-9]+\.[0-9]+" ~/docker-compose.yml')"
    backup_file="pangolin-${pangolin_version}-$(date +%Y%m%d).tar.gz"
    ssh {{pangolin_host}} bash -s -- "$backup_file" <<'REMOTE_SCRIPT'
    cd {{pangolin_dir}} || exit
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
    rsync -avz --progress {{pangolin_host}}:{{pangolin_dir}}/"$backup_file" {{local_dir}}
    echo "Backup pulled locally: $backup_file"
