# Headscale Migration Progress

Updated: 2026-10-05

## Status legend

- `[x]` migration complete — flipped (or already on Headscale), Caddy deployed if needed; HTTPS was verified or explicitly left to Dave, with any known failure recorded; SaaS entry retained unless removal is explicitly approved
- `[~]` in progress or needs attention
- `[ ]` pending

## Canary

- [x] `speedtest-tracker` — flipped, Caddy converged 2026-10-04; root redirects to `/admin/login`, which returns 200 over HTTPS; certificate valid to 2027-01-02; SaaS entry retained

## Needs attention

- [~] `jellyfin` — flipped 2026-10-04 (unplanned, outside batch). On Headscale (100.100.0.6, online). Caddy/HTTPS state UNKNOWN. SaaS entry intentionally kept as rollback path. Decision needed: finish Caddy forward or roll back to SaaS.

## Migrated — HTTPS verified, SaaS entries retained

- [x] `beszel` — flipped 2026-10-05 (100.100.0.17), Caddy-only run succeeded (12 OK, 6 changed); Dave confirmed the HTTPS page loads from Navidrome; SaaS entry retained
- [x] `prowlarr` — flipped 2026-10-04 (100.100.0.7), Caddy deployed; Dave confirmed it works, and the HTTPS login page returns 200; SaaS entry retained by instruction
- [x] `sonarr` — flipped 2026-10-04 (100.100.0.8), service playbook ran (56 OK, 13 changed, 0 failed), Caddy running; Dave confirmed it is working after the canary curl timed out; SaaS entry retained

## Migrated — HTTPS verified or left to Dave

- [x] `radarr` — flipped 2026-10-04 (100.100.0.9); full service playbook succeeded (56 OK, 12 changed, 0 failed); HTTPS verification left to Dave per instruction; SaaS entry retained
- [x] `lidarr` — flipped 2026-10-04 (100.100.0.10); Caddy-only run succeeded (12 OK, 6 changed, 0 failed); HTTPS verification left to Dave per instruction; SaaS entry retained
- [x] `gatus` — flipped 2026-10-04 (100.100.0.11); Caddy-only run succeeded (12 OK, 6 changed, 0 failed); HTTPS verification left to Dave per instruction; SaaS entry retained
- [x] `homepage` — flipped 2026-10-04 (100.100.0.12); Caddy-only run succeeded (12 OK, 6 changed, 0 failed); HTTPS verification left to Dave per instruction; SaaS entry retained
- [x] `qbittorrent` — flipped 2026-10-04 (100.100.0.13); Caddy-only run succeeded (12 OK, 6 changed, 0 failed); HTTPS verification left to Dave per instruction; SaaS entry retained
- [x] `grafana` — flipped 2026-10-04 (100.100.0.14); Caddy-only run succeeded (12 OK, 6 changed, 0 failed); HTTPS verification left to Dave per instruction; SaaS entry retained
- [x] `immich` — flipped 2026-10-04 (100.100.0.15); Caddy-only run succeeded (12 OK, 6 changed, 0 failed); HTTPS verification left to Dave per instruction; SaaS entry retained
- [x] `audiobookshelf` — already online on Headscale (100.100.0.5); tailnet Caddy role wiring removed per Dave; Gatus/Homepage retain the public `audiobookshelf.davegallant.ca` URL; live Caddy container unchanged; SaaS entry retained
- [x] `maloja` — flipped 2026-10-05 (100.100.0.18); Caddy-only run succeeded (12 OK, 6 changed); HTTPS verification left to Dave; SaaS entry retained
- [x] `romm` — already online on Headscale (100.100.0.3); migration playbook skipped the flip; Caddy-only run succeeded (12 OK, 4 changed); HTTPS verification left to Dave; SaaS entry retained
- [x] `upsnap` — flipped 2026-10-05 (100.100.0.19); Caddy-only run succeeded (12 OK, 6 changed); HTTPS verification left to Dave; SaaS entry retained
- [x] `lubelogger` — flipped 2026-10-05 (100.100.0.20); Caddy-only run succeeded (12 OK, 6 changed); first HTTPS check returned a TLS internal error; no further HTTPS checks per Dave's instruction; SaaS entry retained
- [x] `changedetection` — flipped 2026-10-05 (100.100.0.21); Caddy-only run succeeded (12 OK, 6 changed); HTTPS verification left to Dave; SaaS entry retained
- [x] `kiwix` — flipped 2026-10-05 (100.100.0.23); Caddy-only run succeeded (12 OK, 6 changed); HTTPS verification left to Dave; no Gatus/Homepage URL was configured; SaaS entry retained
- [x] `adguard-home` — flipped 2026-10-05 (100.100.0.24); Caddy-only run succeeded (12 OK, 6 changed); HTTPS verification left to Dave; SaaS entry retained
- [x] `watchyourlan` — flipped 2026-10-05 (100.100.0.25); Caddy-only run succeeded (12 OK, 6 changed); HTTPS verification left to Dave; SaaS entry retained
- [x] `dispatcharr` — flipped 2026-10-05 (100.100.0.26); Caddy-only run succeeded (12 OK, 6 changed); HTTPS verification left to Dave; SaaS entry retained
- [x] `invidious` — flipped 2026-10-05 (100.100.0.27); Caddy-only run succeeded (12 OK, 6 changed); HTTPS verification left to Dave; SaaS entry retained

## Pending — wired, ready to migrate

All 22 wired service hosts have completed their Headscale migration and Caddy deployment.

## Separate tracks — not in the batch flow

- `seerr` → public exposure moves to Pangolin (Funnel replacement). Not a Headscale Caddy host.
- `arca` → Caddy goes in the arca repo's own Compose project (not Ansible-managed). Flip arca to Headscale only AFTER its Caddy is ready. `/healthz` is the verification endpoint.
- `lan-orangutan` → REMOVED 2026-10-04 (Dave doesn't use it). Playbook, inventory, homepage, Gatus, vault entries deleted.

## Flip-only hosts — no Serve HTTPS, no Caddy needed

Hosts on the tailnet without Serve HTTPS. Flip via the migration playbook; no Caddy deploy.

- `bedrock`
- `bento-pdf`
- `cinema`
- `forgejo`
- [x] `forgejo-runner` — flipped 2026-10-05 (100.100.0.16), Headscale reports online, Tailscale SSH enabled; runner service active and Forgejo HTTPS returns 200; journal shows successful task polling before the flip, with no post-flip task observed yet; SaaS entry retained
- `gotify`
- `igotify`
- `miniflux`
- `navidrome`
- `paperless-ngx`
- `pinepods`
- `searxng`
- `tailscale-exit-node` (hand-managed; confirm advertised routes before flipping)
- `tailscale-subnet-router` (hand-managed; confirm advertised routes before flipping)
- `umami`

`pangolin` is excluded: it is the off-tailnet edge host, not a node to flip.

## Problem nodes — deferred, separate track

- 6 SSH inspection failures: `ai`, `homeassistant`, `mcleod`, `mullvad-tokyo`, `mullvad-toronto`, `truenas-scale`. `ai` and `homeassistant` refused TCP/22; the other four failed strict ED25519 host-key checks.
- 3 stale/offline SaaS entries: `archivebox`, `hephaestus`, `speedtest-tracker` (the latter is the old SaaS entry for the migrated canary).
- Prune dead entries before migrating; fix SSH on the rest separately.

## Per-host checklist (for each batch)

1. Generate one reusable short-expiry pre-auth key for the batch
2. Flip via `playbooks/migrate-to-headscale/main.yml`
3. Confirm node online in `headscale nodes list`
4. Run the service playbook to converge Caddy (skip for flip-only hosts)
5. Verify `https://<host>.tail.davegallant.ca/` (200, or 3xx to a working page)
6. Update Gatus endpoint and Homepage tile URLs to the Headscale MagicDNS name
   (only after the monitoring host itself can resolve Headscale names —
   otherwise the checks break until gatus/homepage migrate)
7. Expire the batch key
8. Delete the stale SaaS machine entry (only after HTTPS verified)
9. Update this file and commit (one commit per batch)
