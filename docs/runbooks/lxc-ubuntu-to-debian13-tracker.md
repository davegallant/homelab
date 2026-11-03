# LXC Ubuntu to Debian 13 migration tracker

Update this ledger after each approved migration. It records observed state;
the presence of an Ubuntu LXC is a candidate, not authorization to migrate it.
Each container still needs its own Phase 0 receipt and Dave's approval.

Inventory snapshot: 2026-11-02 America/Toronto, read-only `pct list` and
`/etc/os-release` checks on `pve-g3-1` and `pve-g3-2`. The Proxmox hosts reported
UTC timestamps on 2026-11-03. No other containers were changed for this survey.

Cutover addressing preference: use the replacement's new LAN IP by default.
Preserve the current LAN IP for `cinema`, `mullvad-toronto`, and
`mullvad-tokyo`.

## Completed migration

| Service | Proxmox host | New CT | New OS / LAN IP / tailnet IP | Status | Rollback |
|---|---|---:|---|---|---|
| upsnap | pve-g3-2 | 101 | Debian 13 trixie / `192.168.1.64` / `100.100.0.5` | Cut over; UpSnap and Caddy healthy; Alloy active and recent logs present in Loki; Gatus HTTPS probe returned 200 after policy update. Wake test deferred; latest device record showed `hephaestus` offline. | Old CT 102 was removed by Dave. CT ID 102 has since been reused for the Gatus replacement. The old UpSnap Tailnet node/IP remains in Headscale policy state pending separate cleanup. |
| gatus | pve-g3-2 | 102 | Debian 13.6 / `192.168.1.32` / `100.100.0.7` | Cut over to `gatus.tail.davegallant.ca`; HTTPS certificate validates and API returns 200 with 38/38 checks passing. Secondary AdGuard answers DNS on `.7`. Alloy is active and recent Gatus logs are present in Loki. Headscale identity is `gatus` (node ID 77). | Old CT 131, Ubuntu 26.04.1, stopped intact with its data. Old Headscale node ID 11 was removed. |
| adguard-home | pve-g3-2 | 104 | Debian 13.6 / `192.168.1.77` / `100.100.0.9` | Cut over; reserved MAC retained. Authoritative copy matched: 7 files, sizes, ownership/modes, and SHA-256 hashes. AdGuard container running with host networking; LAN and tailnet DNS work over UDP/TCP; LAN and tailnet UI HTTPS return 302 with valid TLS. Gatus CT 102 resolves through the new primary resolver. Alloy is active and fresh `adguard-home` streams are queryable in Loki. Headscale identity `adguard-home`, node ID 78, `tag:monitored`; managed primary/secondary DNS and policy updated. Shared Ansible package task now generates `en_CA.UTF-8`; plain SSH login is clean. | Old CT 126, Ubuntu 26.04.1, stopped intact with its data and Compose file. Old Headscale node ID 24 was removed. No wake/device action applies. |

## In-progress migration

| Service | Old CT | Replacement CT | Current state | Open items |
|---|---|---|---|---|
| bedrock | `pve-g3-1` CT 120, Ubuntu 26.04.1; stopped intact after cutover | `pve-g3-1` CT 103, Debian 13.6 / `192.168.1.7` / `100.100.0.6`; LXC and app running | Phase 2 data copy matched before startup: 12,412 manifest entries, 10,740 files, 661,109,595 bytes, matching file hashes, owners, groups, and modes. New Bedrock container is healthy on the live `2026.10.2` image. Alloy marker log was found in Loki. Cut over to the new LAN IP `192.168.1.7`; Bedrock status query passed (`version=1.26.61`). | No client-facing hostname/route was found. A real player client confirmation on `192.168.1.7` remains pending. Headscale identity is `bedrock` with `tag:monitored`; stopped CT 120 remains available as `bedrock-rollback`. Live policy permits `tag:monitored` to `tag:loki:3100`. CT 120 and its data remain intact. |

## Confirmed running Ubuntu LXC candidates

These containers were observed running Ubuntu 26.04 in the inventory snapshot.
The Alloy column records that snapshot; see the status column for later changes.

| Service | Proxmox host | CT | OS | Alloy | Migration status |
|---|---|---:|---|---|---|
| bedrock | pve-g3-1 | 120 | Ubuntu 26.04 | active, enabled at snapshot | Cut over; old CT 120 stopped intact. See above. |
| adguard-home | pve-g3-2 | 126 | Ubuntu 26.04.1 | active, enabled | Migrated to Debian 13 CT 104 at reserved `.77`; old CT stopped intact and old Headscale node removed. See completed migration. |
| gatus | pve-g3-2 | 131 | Ubuntu 26.04.1 | active, enabled at inventory snapshot | Migrated to CT 102; old CT 131 stopped intact. See completed migration. |
| gotify | pve-g3-2 | 136 | Ubuntu 26.04 | active, enabled | Candidate; Phase 0/go required |
| igotify | pve-g3-2 | 143 | Ubuntu 26.04 | active, enabled | Candidate; Phase 0/go required |

## Other observed running Ubuntu LXCs

These were observed running Ubuntu 26.04 without an Alloy service. Their
migration purpose and management path need review before scheduling.

| Name | Proxmox host | CT | OS | Alloy | Status |
|---|---|---:|---|---|---|
| mullvad-tokyo | pve-g3-1 | 106 | Ubuntu 26.04 | not installed | Needs scope/ownership review |
| rfd-enrich | pve-g3-1 | 141 | Ubuntu 26.04 | not installed | Needs scope/ownership review |
| arca | pve-g3-1 | 144 | Ubuntu 26.04 | not installed | Needs scope/ownership review |
| mullvad-toronto | pve-g3-2 | 127 | Ubuntu 26.04 | not installed | Needs scope/ownership review |

## Stopped containers and unclassified inventory hosts

| Name | Proxmox host | CT | Observed state | Next step |
|---|---|---:|---|---|
| gyb | pve-g3-1 | 117 | Stopped; Proxmox `ostype: ubuntu`; guest version and Alloy status unknown | Dave decides disposition; inspect only if authorized to start it |
| archivebox | pve-g3-1 | 129 | Stopped; Proxmox `ostype: ubuntu`; guest version and Alloy status unknown | Dave decides disposition; inspect only if authorized to start it |

Ansible inventory names not present in the `pct list` output from these two
hosts are: `cinema`, `grafana`, `invidious`, `lidarr`, `paperless-ngx`,
`prowlarr`, `radarr`, `sonarr`, `speedtest-tracker`, and `umami`. Their runtime
placement and whether they are LXCs are unverified; classify them before adding
them to the migration queue.

## Reconcile the remaining-shipper count

The original pilot brief described UpSnap as one of eight remaining LXC Alloy
shippers. This snapshot confirms five other running Ubuntu LXCs with Alloy
active on the two inventoried Proxmox hosts. Three of the previously counted
shippers are not identified by this two-host snapshot, or the earlier count
used a different scope. Reconcile the complete LXC/Alloy inventory before
calling this ledger exhaustive.

## Update procedure

After a migration, update the row with the new CT ID, verified OS, addresses,
Alloy/Loki result, final route, wake-test status, and old rollback CT state. Keep
the rollback row until Dave separately approves deletion. Record unknowns as
unknown instead of inferring them from inventory names or Proxmox `ostype`.
