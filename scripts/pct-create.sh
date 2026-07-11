#!/usr/bin/env bash
set -euo pipefail

# --- config you may want to tweak ---
TEMPLATE="proxmox-iso:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
ROOTFS_STORAGE="local-lvm"   # where the container's disk will live
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

# --- get next free ctid, same as the GUI does ---
ctid="$(pvesh get /cluster/nextid)"
echo "Using next available CTID: ${ctid}"

# --- create the container ---
pct create "${ctid}" "${TEMPLATE}" \
  --hostname="${ctname}" \
  --ostype=ubuntu \
  --unprivileged=1 \
  --features=nesting=1 \
  --net0=name=eth0,bridge=${BRIDGE},ip=dhcp \
  --arch=amd64 \
  --cores=${CORES} \
  --memory=${MEMORY} \
  --swap=${SWAP} \
  --rootfs=${ROOTFS_STORAGE}:${DISK_SIZE} \
  --storage="${ROOTFS_STORAGE}"

# --- append raw lxc config (tun/tap device passthrough) ---
CONF="/etc/pve/lxc/${ctid}.conf"
cat >> "${CONF}" <<EOF
lxc.cgroup2.devices.allow: c 10:200 rwm
lxc.mount.entry: /dev/net dev/net none bind,create=dir
EOF

echo "Container ${ctid} (${ctname}) created."
echo "Config written to ${CONF}:"
tail -n 2 "${CONF}"

read -rp "Start container now? [y/N] " start_now
if [[ "${start_now,,}" == "y" ]]; then
  pct start "${ctid}"
  echo "Started ${ctid}."
fi
