#!/usr/bin/env bash
# pve-update-nodes.sh — apt update && apt upgrade -y on every Proxmox node
set -euo pipefail

NODES=(
  pve-g3-1
  pve-g3-2
  pve-apollo
)

LOG_DIR="logs/pve-update-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${LOG_DIR}"

FAILED=0

for node in "${NODES[@]}"; do
  log_file="${LOG_DIR}/${node}.log"
  echo "== ${node} (log: ${log_file}) =="
  if ssh "root@${node}" "apt-get update -y && apt-get upgrade -y" 2>&1 | tee "${log_file}"; then
    echo "  ✓ ${node}"
  else
    echo "  ✗ ${node}"
    FAILED=$((FAILED + 1))
  fi
  echo ""
done

if [[ $FAILED -eq 0 ]]; then
  echo "All nodes updated successfully."
else
  echo "${FAILED} node(s) failed." >&2
  exit 1
fi
