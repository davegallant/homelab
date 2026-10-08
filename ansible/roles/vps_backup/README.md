# vps_backup

Nightly encrypted backups of the Pangolin VPS state to Google Drive.
[Restic](https://restic.net) encrypts and dedups locally, then ships snapshots
to Drive through its [rclone backend](https://restic.net/manual/040_backup.html).
Same simple end of the spectrum (deliberately not PBS) — and the same
pattern Dave's TrueNAS backups already use.

## What gets backed up

Everything under `~/config` that Ansible does **not** manage (i.e. not in git):

| Staged as | Source | Contents |
|---|---|---|
| `headscale-db.sqlite` | `~/config/headscale/data/db.sqlite` | Headscale DB: nodes, routes, policy — the whole tailnet state |
| `pangolin-db.sqlite` | `~/config/db/db.sqlite` | Pangolin DB: sites, resources, users |
| `files/noise_private.key` | `~/config/headscale/data/noise_private.key` | Headscale identity key (a restored Headscale needs this) |
| `files/gerbil.key` | `~/config/key` | Gerbil WireGuard private key |
| `files/acme.json` | `~/config/letsencrypt/acme.json` | Traefik certs (renewable, but avoids rate limits on rebuild) |
| `files/config.yaml`, `files/policy.hujson` | `~/config/headscale/` | Headscale config (also in git, harmless to include) |

SQLite files are copied with `sqlite3 .backup` first, so the snapshot is
consistent while the services keep running. Everything else on the VPS
(compose file, templated configs) is rebuilt from this repo. Data is tens of
MB — Drive's 15 GB free tier is plenty.

## Prerequisites

1. You already have an rclone `gdrive` remote on your Mac — no OAuth needed.
   (If the token ever expires, reconnect it with `rclone config`.)
2. Copy the `[gdrive]` stanza from `~/.config/rclone/rclone.conf` into the
   Ansible vault as `vps_backup_rclone_config` (Codex handles vault edits —
   never put the token in plaintext). The stanza name must match
   `vps_backup_rclone_remote`.
3. Add a restic password to the vault:
   ```yaml
   vps_backup_restic_password: "<output of: openssl rand -base64 32>"
   ```
4. In the Gotify UI, create an app for VPS backups and add its token to the
   vault:
   ```yaml
   vps_backup_gotify_token: "<app token>"
   ```
   Set `vps_backup_gotify_url` to your public Gotify URL (e.g. in
   `group_vars/all/vars.yaml`). Leave it empty to disable failure alerts.
5. Run the pangolin playbook (role is wired in at the end of
   `ansible/playbooks/pangolin/main.yml`).

## Failure alerts

Any failure in the backup script posts to Gotify at priority 8 and exits
non-zero; success is silent. A fully-dead VPS is already covered by the
existing Gatus check, so this only catches backup-level failures (restic,
rclone/auth, sqlite dump).

## Verify

```sh
ssh pangolin "set -a; . /etc/vps-backup/restic.env; set +a; restic snapshots"
ssh pangolin "systemctl list-timers vps-backup.timer"
```

You should also see the `vps-backup` folder appear in Google Drive after the
first run.

## Restore

```sh
# 1. Restore the latest snapshot to scratch (staging dir name varies per backup;
#    find the files after restore).
ssh pangolin "set -a; . /etc/vps-backup/restic.env; set +a; restic restore latest --target /tmp/vps-restore && find /tmp/vps-restore -type f"

# 2. Stop the stack (compose project 'pangolin', compose file at ~/docker-compose.yml).
ssh pangolin "docker compose -f ~/docker-compose.yml -p pangolin down"

# 3. Copy state back into place, e.g.:
ssh pangolin "cp /tmp/vps-restore/<staging>/headscale-db.sqlite ~/config/headscale/data/db.sqlite"
ssh pangolin "cp /tmp/vps-restore/<staging>/pangolin-db.sqlite ~/config/db/db.sqlite"
# ... same pattern for files/ (noise_private.key, gerbil.key, acme.json)

# 4. Start the stack again.
ssh pangolin "docker compose -f ~/docker-compose.yml -p pangolin up -d"
```

Fix ownership/permissions to match the originals if anything looks off
(`0600` on keys, `0640` on configs per `main.yml`).

## Disaster recovery (full VPS rebuild)

If the VPS is lost entirely: the repo rebuilds the machine, the Drive backup
restores the state.

1. **New VPS + DNS.** Provision a fresh Ubuntu VPS. If the IP changed, update
your `~/.ssh/config` `pangolin` alias (and `ssh-keygen -R` the old host key),
and update DNS for the VPS's public hostnames.

2. **Pull the state down** (as root on the new VPS):
   ```sh
   apt update && apt install -y restic rclone
   mkdir -p /root/.config/rclone
   # from your Mac:
   scp ~/.config/rclone/rclone.conf pangolin:/root/.config/rclone/rclone.conf
   # back on the VPS:
   export RESTIC_REPOSITORY=rclone:gdrive:vps-backup
   export RESTIC_PASSWORD='...'   # from the vault
   restic restore latest --target /tmp/vps-restore
   ```

3. **Lay the state into place**:
   ```sh
   mkdir -p ~/config/headscale/data ~/config/db ~/config/letsencrypt
   S=$(dirname $(find /tmp/vps-restore -name 'headscale-db.sqlite' | head -1))
   cp $S/headscale-db.sqlite ~/config/headscale/data/db.sqlite
   cp $S/pangolin-db.sqlite ~/config/db/db.sqlite
   cp $S/files/noise_private.key ~/config/headscale/data/
   cp $S/files/gerbil.key ~/config/key
   cp $S/files/acme.json ~/config/letsencrypt/
   chmod 600 ~/config/key ~/config/headscale/data/noise_private.key
   ```

4. **Run the playbook** from your Mac (`cd ansible && just run "--limit pangolin"`).
It recreates directories (idempotent), templates the compose file and configs
from git, installs Docker, and brings the stack up **with the restored state
already in place** — and reinstalls the backup timer, so backups resume
automatically.

5. **Verify**:
   ```sh
   ssh pangolin "docker exec headscale headscale nodes list | head"
   ```
   Nodes check back in on their own (restored Noise key = same Headscale
identity; restored policy DB included). The monitoring endpoint should go
green, tunnel sidecars reconnect once DNS is correct, and the restored
`acme.json` means no certificate re-issuance.

Not covered by the backup (deliberately): the VPS's SSH host keys (fresh ones
are fine — `ssh-keygen -R` on your Mac) and anything outside `~/config`, which
is all rebuilt from this repo.
