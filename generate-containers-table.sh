#!/usr/bin/env bash

# Script to generate a Markdown table of container images and their tags
# used in all docker-compose.yml files, and inject it into README.md.
#
# Requires git and yq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
README_FILE="${SCRIPT_DIR}/README.md"
TABLE_FILE=$(mktemp)

trap 'rm -f "$TABLE_FILE"' EXIT

generate_table() {
  echo "| Image | Version |"
  echo "|-------|---------|"

  # Find all docker-compose.yml files tracked by git
  git ls-files | grep "docker-compose.yml$" | while read -r compose_file; do
    yq eval '.services | keys' "$compose_file" | sed 's/^- //' | while read -r service; do
      image=$(yq eval ".services.\"$service\".image" "$compose_file" 2>/dev/null)
      if [[ -n "$image" && "$image" != "null" ]]; then
        version=$(echo "$image" | awk -F':' '{print $2}')
        version=${version:-"latest"}
        image=$(echo "$image" | awk -F':' '{print $1}')
        echo "| $image | $version |"
      fi
    done
  done | sort -u
}

generate_table > "$TABLE_FILE"

# Build new README: before marker + marker + table + end marker + after marker
{
  sed -n '1,/<!-- DOCKER_SERVICES_START -->/p' "$README_FILE"
  cat "$TABLE_FILE"
  sed -n '/<!-- DOCKER_SERVICES_END -->/,$p' "$README_FILE"
} > "${README_FILE}.tmp" && mv "${README_FILE}.tmp" "$README_FILE"

echo "Updated ${README_FILE} with $(wc -l < "$TABLE_FILE" | tr -d ' ') lines (including header)"
