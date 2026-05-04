pangolin_host := "pangolin"
pangolin_dir := "~"
pangolin_version := `ssh pangolin "grep -oP 'fosrl/pangolin:\\K[0-9]+\\.[0-9]+\\.[0-9]+' ~/docker-compose.yml"`

date := `date +%Y%m%d`
backup_file := "pangolin-" + pangolin_version + "-" + date + ".tar.gz"
local_dir := "/mnt/synology-2b/backups/pangolin"

# Show available recipes
default:
    @just --list

# Backup pangolin config from remote host and pull locally
backup-pangolin:
    ssh {{pangolin_host}} "cd {{pangolin_dir}} && docker compose stop pangolin && tar -czvf {{backup_file}} config/ docker-compose.yml; [ $? -le 1 ] && docker compose start pangolin && exit 0"
    rsync -avz --progress {{pangolin_host}}:{{pangolin_dir}}/{{backup_file}} {{local_dir}}
    @echo "Backup pulled locally: {{backup_file}}"
