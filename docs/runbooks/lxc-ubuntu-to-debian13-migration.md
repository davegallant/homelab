# Ubuntu to Debian 13 LXC migration

Use this runbook for one service LXC per migration. Replace an Ubuntu container
with a fresh Debian 13 container; never convert Ubuntu in place. The old
container is the rollback copy and remains stopped, intact, and undeleted until
Dave separately approves its deletion after the replacement has proven itself.

Current progress is tracked in
[lxc-ubuntu-to-debian13-tracker.md](lxc-ubuntu-to-debian13-tracker.md).

## Operating rules

- Dave approves each phase before it starts. Phase 0 ends with an inventory
  receipt and a wait for approval; it does not create or change anything.
- On any operational failure, preserve both states and evidence, report the
  failure, and wait. Do not retry, roll back, clean caches, delete, or invent a
  workaround without Dave's in-the-moment direction.
- Diagnose in this order: observe live state, read the relevant documentation,
  then conclude. A log line is a hypothesis until documentation or a
  reproducing check confirms it. If no documentation covers it, write
  “untested, not guilty” and name the verification step.
- Use exact IDs, hosts, paths, bridge, template names, IPs, image tags, and
  credentials from live evidence. Never infer them from a service name.
- Never print Vault values, Tailscale pre-auth keys, tokens, private keys, or
  other secrets. Do not edit Vault. Do not claim this distro migration fixes a
  Proxmox host-kernel CVE; LXCs share the host kernel.
- Keep the scope to the approved service. Do not alter other LXCs, Proxmox
  hosts, the VPS, or the Loki sidecar unless Dave explicitly approves the
  specific change. Repo changes to Ansible playbooks are separate from a
  migration phase unless Dave explicitly includes them.
- Cut over to the replacement's new LAN IP by default. Preserve the current
  LAN IP for `cinema`, `mullvad-toronto`, and `mullvad-tokyo`; do not apply the
  new-IP default to those services.
- AdGuard Home is another address-preservation exception: keep
  `192.168.1.77` and its OPNsense-reserved MAC. Use a different MAC/IP while
  testing the replacement; reuse the old MAC only after the old LXC is stopped
  at cutover.

## Proven operational pitfalls

- The repo's default `ansible/.vault_pass` may be a mode `0600` regular file,
  not an executable script. Ansible accepts it with `--vault-password-file`,
  as the repo's `just` recipes do. Do not require `test -x`; do not make
  temporary playbook creation conditional on that check.
- A fresh Debian 13 template can have package indexes that refer to package
  versions no longer present on the mirror. `install-docker.yml` installs
  Python before its later APT cache update, so an initial install can fail with
  mirror 404s. With Dave's in-the-moment go, run `apt-get update` once inside
  the replacement and retry the installer once. If the retry fails, preserve
  the output and stop; do not clean the APT cache. This was reproduced on
  AdGuard CT 104 on 2026-11-03: the update succeeded and the single retry
  completed.
- A DHCP-configured LXC may not have its address during the first immediate
  `ip` check after `pct start`. Check the guest's `dhclient` journal and
  interface state before concluding DHCP failed. On AdGuard CT 104, OPNsense
  assigned `192.168.1.99` one second after the initial check.
- Debian LXCs must have the operator's SSH locale generated. The SSH client
  sends `LC_CTYPE`/`LC_COLLATE` as accepted by sshd; if those locales are not
  installed, Bash prints repeated `setlocale` warnings at login. Verify with
  `locale -a`, `/etc/locale.gen`, and `sshd -T | grep acceptenv`. Ensure the
  `locales` package is installed, enable `en_CA.UTF-8 UTF-8` in
  `/etc/locale.gen`, and run `locale-gen en_CA.UTF-8`. Verify a plain interactive
  `ssh root@<SERVICE>` login has no locale warnings. The shared
  `install-common-packages.yml` task now manages this for service playbooks.
- The root login shell on `pve-g3-2` is fish. Bash-only shell options such as
  `set -o pipefail` fail there. For a remote pipeline, invoke Bash explicitly
  or run the pipeline locally; verify the copied data after any ambiguous
  command result.
- When an OPNsense DHCP reservation binds a required address to a MAC, do not
  attach that MAC to the replacement while the old LXC is still connected.
  Use a temporary MAC and DHCP address during coexistence, then reuse the old
  MAC only after stopping the old LXC at cutover. Verify that OPNsense assigns
  the required address before starting the replacement's DNS service there.
- Use `ssh root@<PVE_HOST> pct exec <CTID> -- ...` as the stable path into a
  newly created LXC. The service playbook may enable UFW with deny-incoming
  before the replacement joins Tailscale, so direct SSH to its LAN IP may stop
  working. Do not mistake that for a Proxmox ACL failure. Compare SSH key
  fingerprints before changing `authorized_keys`; an agent host-key-binding
  warning is non-fatal when SSH later reports successful authentication.
- A read-only CLI syntax error has no infrastructure effect: read that
  subcommand's help, correct the query, and continue. Reserve HALT AND PRESERVE
  for failed mutations, failed verification, or state that cannot be
  established safely. Do not repeat a failed mutation without Dave's go.
- Headscale 0.29.7 `preauthkeys list` has no `--user` option. List keys without
  that filter and select only safe metadata client-side; never print the key
  field. Confirm the exact user ID and tag from live Headscale state before
  creating a one-use key.
- If a one-use Headscale key is created with `--tags tag:<service-role>`, do
  not also pass `--advertise-tags` to `tailscale up`. Headscale's empty
  `tagOwners` entries reject a node's separate tag request even when the
  registration key already carries that tag. Check the key's `acl_tags`, then
  verify the enrolled node's tag and Tailscale IP. Add any temporary hostname
  to `headscale_node_tags` before running the managed policy/tag play.
- `alloy.service` being active does not prove Loki ingestion. If the rendered
  Loki destination is tailnet-only, confirm the replacement is enrolled with
  a tag the live ACL permits, that `loki` resolves from the replacement, and
  that a recent stream for its hostname appears in Loki. Do not change the
  ACL when the existing tag rule already grants this path.
- Keep auth-key creation and use under `no_log`. Preserve useful failure
  evidence through separate status/log queries that contain no key; do not
  hide all diagnostics behind a failing `no_log` assertion. A task marked
  `changed` is not proof that Tailscale enrollment succeeded.
- Headscale pre-auth keys use Headscale's user ID, not a node's `user.id`.
  For AdGuard, the old tagged node reported special user ID `2147455555`, but
  `headscale users list` showed the actual key owner `dave` as ID `1`; using the
  node ID for key creation failed before producing a key. Confirm the user with
  `headscale users list`, create the one-use tagged key for that user, and verify
  the enrolled node's final name, tailnet IP, and tags.
- When a replacement receives a reused Tailnet IP, its SSH host key is expected
  to differ from the retired container. Verify the replacement's public-key
  fingerprint through the Proxmox console before refreshing the operator's
  `known_hosts` entry; never disable strict host-key checking.
- Caddy may initially return a TLS handshake error while its DNS-01 certificate
  request is still running. Read Caddy logs and wait for `certificate obtained
  successfully`, then verify the hostname with a normal trusted HTTPS request.
- Resolve the configured Loki hostname from the replacement before probing the
  endpoint. For AdGuard, `loki` resolved to `100.100.0.1`; probing an assumed
  address produced an ACL rejection unrelated to Alloy. Confirm a recent Loki
  stream with the replacement's host label to prove ingestion.

## Phase 0: read-only inventory

Read the repo's `AGENTS.md`, the service's inventory entry, its playbook and
Compose file, shared task files, and the relevant runbooks. Check for Ubuntu-only
assumptions before creating a Debian container. If the playbook needs edits for
Debian 13, report the exact changes needed and stop; do not edit it in this
migration.

From the verified Proxmox host, identify the container and record:

- CT ID, Proxmox host, current status, template/OS version, CPU, memory, root
  disk, unprivileged/privileged mode, nesting/keyctl features, bridge, IP, and
  VLAN.
- App Compose path, image tag/digest, host data path and container mount,
  non-secret environment settings, listen address, scan range/interval/time
  zone, and reverse-proxy/tailnet route.
- Alloy service/config path, Loki destination, and current shipping status.
- The documented SSH/Ansible path to the Proxmox host, LXC, and any control
  plane needed for cutover. The repo documents the VPS as plain SSH through the
  operator's `~/.ssh/config`; do not assume a Proxmox-to-VPS SSH hop. Never
  bypass host-key checking.

Useful read-only checks, after substituting values observed from inventory:

```sh
ssh root@<PVE_HOST> pct list
ssh root@<PVE_HOST> pct config <OLD_CTID>
ssh root@<PVE_HOST> pct exec <OLD_CTID> -- cat /etc/os-release
ssh root@<OLD_LXC> docker ps
ssh root@<OLD_LXC> docker compose -f <COMPOSE_PATH> config --services
ssh root@<OLD_LXC> systemctl show alloy.service --property=LoadState,ActiveState,UnitFileState
```

Do not print full Compose-rendered environment or `docker inspect` environment
output if it might contain secrets. Record only the needed non-secret fields.
For container facts, prefer explicit `pct config` fields and `cat
/etc/os-release` over guesses. If a container is stopped, do not start it just to
inventory it; mark its OS version unassessed.

Finish Phase 0 with a source-linked inventory receipt and wait for Dave's go.

## Phase 1: prepare a fresh Debian 13 LXC

Start only after Dave approves Phase 1. Use the Debian 13 template actually
listed on the verified Proxmox host. Create the replacement on the same host,
bridge, and container features as the old LXC, matching its CPU, memory, and
disk. Give it a different LAN IP so both containers can coexist. Record the
new CT ID and IP.

Install Docker using the existing service playbook when it is Debian 13 safe;
otherwise follow the project's documented Debian 13 Docker installation. Do
not change Ubuntu APT sources or convert the old container. If APT or Ansible
fails, preserve the failure output and stop under the operating rules above.

Copy the Compose file and create empty production data directories using the
paths and settings captured in Phase 0. Keep the production app stopped. If
Dave explicitly approves a pre-copy to reduce cutover time, copy the live data
to separate staging directories and test only from that staged copy on the
temporary address. A live pre-copy is not authoritative and must not be
reported as an exact match. Verify Docker and host networking if the service
requires it. Stop and report the new CT ID/IP for Dave's Phase 1 review.

## Phase 2: copy data and verify the replacement

Start only after Dave approves Phase 2.

1. Reconfirm the old stack and data source paths from Phase 0. Stop only the
   old app stack with `docker compose down` inside the old LXC; leave the old
   LXC itself running for now.
2. Copy the authoritative data with numeric ownership, ACLs, and extended
   attributes into the clean production paths. If an approved live pre-copy
   exists, do not use its test directories as the final destination. For
   example, once the exact hosts and paths are verified:

   ```sh
   ssh root@<OLD_LXC> 'tar --numeric-owner --acls --xattrs -cpf - -C <OLD_DATA_DIR> .' \
     | ssh root@<NEW_LAN_IP> 'tar --numeric-owner --same-owner --same-permissions --acls --xattrs -xpf - -C <NEW_DATA_DIR>'
   ```

3. Compare sorted relative file lists, sizes, numeric ownership, modes, and
   SHA-256 hashes. Include database WAL/SHM files if present. Source and copy
   must match before the new app starts.
4. Start the new stack and verify container health, UI/API, device count and
   names, ping/status updates, and cron schedules against Phase 0. A device
   wake test requires Dave to name that exact device in chat. Never wake all
   devices or expand the configured scan range.
5. Install/verify Alloy as below. Confirm recent logs for the new host in Loki;
   otherwise report the exact gap. Do not invent a different logging path.

If any check fails, preserve both containers and stop. Do not restart the old
app or modify the old LXC without Dave's go.

### Apply Alloy without replaying unrelated service tasks

The service playbook includes `ansible/tasks/install-alloy.yml`. If the normal
playbook has not been applied to the replacement, run that existing task file
alone through a temporary playbook. This avoids replaying Docker Compose,
Beszel, firewall, or proxy tasks. Use the repo's Vault password file without
printing any secret; point `ansible_host` at the verified new LAN IP.

The temporary play should include only:

```yaml
---
- name: Install Alloy only on the replacement
  hosts: <SERVICE_INVENTORY_HOST>
  tasks:
    - ansible.builtin.include_tasks:
        file: <ABSOLUTE_REPO_PATH>/ansible/tasks/install-alloy.yml
```

Remove the temporary playbook after the run. Verify `alloy.service` is loaded,
enabled, and active; confirm the rendered Loki URL without exposing credentials;
check Loki `/ready`; then query recent streams for the new host label. A running
service or reachable Loki endpoint alone does not prove ingestion.

If the Loki endpoint is tailnet-only and the old service identity must remain
active until cutover, install and configure Alloy in Phase 2 but report Loki
ingestion as pending. Do not enroll a temporary or rollback-named Headscale
node just to test shipping. At cutover, remove the verified old Headscale node
first, then enroll the replacement under the final service name and tag; verify
Loki ingestion immediately afterward. Do not rely on installing Alloy alone.

## Phase 3: route cutover

Start only after Dave confirms Phase 2 verification. Keep the replacement's new
LAN IP and update the service route or clients to use it, except for `cinema`,
`mullvad-toronto`, and `mullvad-tokyo`, which retain their current LAN IP. The
old LXC must be stopped after cutover and remain intact.

For the tailnet Caddy pattern used by UpSnap:

1. If Phase 2 did not already enroll the replacement for Alloy, enroll it in
   Headscale using a short-lived, one-use pre-auth key with the verified
   service tags. Pass the key through a protected variable/stdin path; never
   print it. If the key carries the tags, omit `--advertise-tags` from
   `tailscale up`. Install Tailscale through the documented package process
   and verify the assigned tailnet IP.
2. Run only the existing `tailnet_caddy` role against the new inventory target,
   overriding `ansible_host` with the verified new LAN IP. Keep all secret tasks
   under their existing `no_log` handling.
3. Before DNS changes, request the service domain directly at the new tailnet
   IP with `curl --resolve`; verify certificate, UI, and API health.
4. If the MagicDNS name is moving between nodes, read the live Headscale node
   list and resolve the exact old node ID by name. Remove the old Headscale
   node first, then enroll the replacement with the final service name and
   managed tag. Do not create rollback names or guess node IDs. Verify with
   `tailscale dns query <FQDN> A`.
5. Before the DNS move, inspect managed ACLs for clients such as Gatus that
   connect to a pinned tailnet IP. Add the new IP to both the relevant allow
   rule and its policy test, retaining the old IP for rollback. Apply only the
   policy tag with `just run main --limit vps --tags headscale_policy`; verify
   the live policy and a request from the restricted client.
6. Verify the final hostname, HTTPS/UI/API, device list, and monitoring route.
   Then stop the old LXC from its verified Proxmox host. Do not delete it or its
   data. If Dave deferred the wake test, report that acceptance item as pending.

If a route or client configuration is needed to use the selected address,
update only the observed service route. If DNS, proxy ownership, ACLs, or
authentication are unclear, stop and ask with the observed state.

## Receipt

Report the verdict first, then:

- Phase 0 inventory with source/command evidence.
- New CT ID/IP and preparation checks.
- Source/copy file manifest comparison and Phase 2 checklist.
- Cutover method, final LAN and tailnet addresses, and exact commands run.
- UI/API, device count/names, ping, cron, Alloy/Loki, and wake-test status.
- Rollback CT status and open items. Never state that the kernel CVE was fixed
  by replacing an LXC's userspace OS.
