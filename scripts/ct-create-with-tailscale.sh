#!/usr/bin/env bash
# Creates a new LXC container with tun/tap device passthrough (needed for
# tailscale) via pvectl instead of `pct` — works from any machine with
# `pvectl setup` run, not just on the Proxmox host — then installs
# tailscale once the container is up.
#   ./scripts/ct-create-with-tailscale.sh
set -euo pipefail

# --- config you may want to tweak ---
NODE=""                                                              # leave empty to pick interactively
TEMPLATE="proxmox-iso:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"  # leave empty to pick interactively
STORAGE="local-lvm"                                                  # leave empty to pick interactively
BRIDGE="vmbr0"
MEMORY=2048
SWAP=1024
CORES=2
DISK_SIZE=8   # GB

# --- prompt for hostname ---
read -rp "Enter container name (hostname): " ctname
if [[ -z "${ctname}" ]]; then
  echo "Container name cannot be empty." >&2
  exit 1
fi

# --- create the container. --start=false so we control the start prompt
# ourselves, below — the tun/tap lines need to land before first boot. ---
create_args=(
  ct create
  --hostname "${ctname}"
  --cores "${CORES}"
  --memory "${MEMORY}"
  --swap "${SWAP}"
  --disk-size "${DISK_SIZE}"
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp"
  --unprivileged
  --features nesting=1
  --arch amd64
  --start=false
)
[[ -n "${NODE}" ]] && create_args+=(--node "${NODE}")
[[ -n "${TEMPLATE}" ]] && create_args+=(--template "${TEMPLATE}")
[[ -n "${STORAGE}" ]] && create_args+=(--storage "${STORAGE}")

pvectl "${create_args[@]}"

# --- append raw lxc config (tun/tap device passthrough) ---
# Proxmox's REST API doesn't expose raw lxc.* directives at all, so
# `pvectl ct config append` falls back to an SSH file write on the node
# instead of the API `pct create` itself used. See `pvectl ct config
# append --help`.
#
# Proxmox's /cluster/resources (what pvectl's name lookup queries) is
# refreshed periodically by pvestatd, not instantly on creation — a lookup
# right after create can race that refresh and come up empty, so retry for
# a few seconds instead of failing immediately.
for attempt in $(seq 1 10); do
  if pvectl ct config append "${ctname}" \
    --line "lxc.cgroup2.devices.allow: c 10:200 rwm" \
    --line "lxc.mount.entry: /dev/net dev/net none bind,create=dir"; then
    break
  fi
  if [[ "${attempt}" -eq 10 ]]; then
    echo "error: ${ctname} still not visible to pvectl after creation — try re-running:" >&2
    echo "  pvectl ct config append ${ctname} --line \"lxc.cgroup2.devices.allow: c 10:200 rwm\" --line \"lxc.mount.entry: /dev/net dev/net none bind,create=dir\"" >&2
    exit 1
  fi
  sleep 3
done

echo "Container ${ctname} created with tun/tap passthrough configured."

pvectl ct start "${ctname}"

# --- install tailscale ---
# There's no Proxmox API (or pvectl command) for running a command inside
# a container — `pct exec` already does exactly this over the same SSH
# connection `config append` uses above, so no pvectl wrapper is needed.
#
# pct_exec passes the whole remote command as a single argv string to ssh,
# not as separate words — ssh joins all of its trailing arguments together
# with plain spaces before handing them to the remote shell, so anything
# with a pipe/&&/redirect inside `sh -c '...'` loses its quoting and gets
# re-split by the remote shell if passed as multiple argv words instead
# (confirmed the hard way: `curl -fsSL ... | sh` came out as the remote
# shell running "-fsSL" as $0, "curl: not found").
pct_exec() {
  local node="$1" vmid="$2" remote_cmd="$3"
  # shellcheck disable=SC2029 # intentional: substitute vmid/remote_cmd locally into one string
  ssh "${node}" "pct exec ${vmid} -- sh -c '${remote_cmd}'"
}

echo "resolving ${ctname}'s node/vmid..."
node="" vmid=""
for attempt in $(seq 1 10); do
  read -r vmid _ node _ < <(pvectl ct list | awk -v name="${ctname}" '$2==name{print; exit}')
  [[ -n "${node}" ]] && break
  sleep 1
done
if [[ -z "${node}" ]]; then
  echo "error: could not resolve ${ctname}'s node via \`pvectl ct list\`" >&2
  exit 1
fi

echo "waiting for ${ctname} (${vmid}) on ${node} to become reachable..."
for attempt in $(seq 1 30); do
  if pct_exec "${node}" "${vmid}" "true" 2>/dev/null; then
    break
  fi
  if [[ "${attempt}" -eq 30 ]]; then
    echo "error: ${ctname} did not become reachable via pct exec in time — install tailscale manually with:" >&2
    echo "  ssh ${node} \"pct exec ${vmid} -- sh -c 'curl -fsSL https://tailscale.com/install.sh | sh'\"" >&2
    exit 1
  fi
  sleep 2
done

echo "ensuring curl is installed on ${ctname}..."
if ! pct_exec "${node}" "${vmid}" "command -v curl >/dev/null 2>&1"; then
  if ! pct_exec "${node}" "${vmid}" "apt-get update && apt-get install -y curl"; then
    echo "error: failed to install curl on ${ctname} — install it manually, then re-run:" >&2
    echo "  ssh ${node} \"pct exec ${vmid} -- sh -c 'apt-get update && apt-get install -y curl'\"" >&2
    exit 1
  fi
fi

echo "installing tailscale on ${ctname}..."
if ! pct_exec "${node}" "${vmid}" "curl -fsSL https://tailscale.com/install.sh | sh"; then
  echo "error: tailscale install failed — retry manually with:" >&2
  echo "  ssh ${node} \"pct exec ${vmid} -- sh -c 'curl -fsSL https://tailscale.com/install.sh | sh'\"" >&2
  exit 1
fi

echo "tailscale installed on ${ctname}. Bring it up with:"
echo "  ssh ${node} \"pct exec ${vmid} -- tailscale up\""
