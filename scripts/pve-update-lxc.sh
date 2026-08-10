#!/usr/bin/env bash
# pve-update-lxc.sh — apt update && apt upgrade -y on every running LXC
# container across all Proxmox nodes. Stopped containers are skipped; non-apt
# containers are skipped with a note. Per-container logs go to a timestamped
# directory.
set -euo pipefail

NODES=(
  pve-g3-1
  pve-g3-2
  pve-apollo
)

LOG_DIR="logs/pve-update-lxc-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${LOG_DIR}"

UPDATED=0
FAILED=0
SKIPPED_NO_APT=0
SKIPPED_STOPPED=0

for node in "${NODES[@]}"; do
  printf '=== %s ===\n' "${node}"

  # Get the list of all containers and their statuses from this node.
  ct_info=$(ssh "root@${node}" "pct list" 2>/dev/null | awk 'NR>1 {print $1, $2, $NF}') || {
    echo "  ✗ failed to connect to ${node}"
    FAILED=$((FAILED + 1))
    echo ""
    continue
  }

  if [[ -z "${ct_info}" ]]; then
    echo "  no containers on this node"
    echo ""
    continue
  fi

  while read -r ct status name; do
    [[ -z "${ct}" ]] && continue

    if [[ "${status}" != "running" ]]; then
      printf '  %-5s %-20s - %s, skipping\n' "${ct}" "${name}" "${status}"
      SKIPPED_STOPPED=$((SKIPPED_STOPPED + 1))
      continue
    fi

    log_file="${LOG_DIR}/${node}-ct${ct}.log"
    printf '  %-5s %-20s ' "${ct}" "${name}"

    # Check whether apt-get exists inside the container.
    if ssh -n "root@${node}" \
      "pct exec ${ct} -- sh -c 'command -v apt-get >/dev/null 2>&1'" 2>/dev/null; then
      echo "updating..."
      if ssh -n "root@${node}" \
        "pct exec ${ct} -- sh -c 'apt-get update -y && apt-get upgrade -y'" \
        2>&1 | tee "${log_file}"; then
        echo "  ✓ done"
        UPDATED=$((UPDATED + 1))
      else
        echo "  ✗ failed (log: ${log_file})"
        FAILED=$((FAILED + 1))
      fi
    else
      echo "- no apt-get, skipped"
      SKIPPED_NO_APT=$((SKIPPED_NO_APT + 1))
    fi
  done <<< "${ct_info}"

  echo ""
done

echo "Summary: ${UPDATED} updated, ${FAILED} failed, ${SKIPPED_NO_APT} skipped (no apt-get), ${SKIPPED_STOPPED} skipped (not running)"

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
