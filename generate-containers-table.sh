#!/usr/bin/env bash

# Script to generate a Markdown table of container images and their tags
# used in Compose files and Kubernetes configuration, and inject it into README.md.
#
# Requires git, jq, and yq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
README_FILE="${SCRIPT_DIR}/README.md"
TABLE_FILE=$(mktemp)

trap 'rm -f "$TABLE_FILE"' EXIT

generate_table() {
  echo "| Image | Version |"
  echo "|-------|---------|"

  image_row() {
    local image="$1"
    local no_digest image_path version

    [[ -n "$image" && "$image" != "null" ]] || return 0
    no_digest="${image%@*}"
    image_path="${no_digest##*/}"
    if [[ "$image_path" == *:* ]]; then
      version="${image_path##*:}"
      image="${no_digest%:*}"
    else
      version="latest"
      image="$no_digest"
    fi
    echo "| $image | $version |"
  }

  {
    # Find all Compose files tracked by git.
    git ls-files | grep 'docker-compose.yml$' | while read -r compose_file; do
      yq eval '.services | keys | .[]' "$compose_file" | while read -r service; do
        image=$(yq eval ".services.\"$service\".image" "$compose_file" 2>/dev/null)
        image_row "$image"
      done
    done

    # Kubernetes values and manifests use image strings, *_image variables, or
    # image objects with repository/tag fields. Only tracked YAML is considered.
    git ls-files | grep '^kubernetes/.*\.yaml$' | grep -v '/templates/' | while read -r yaml_file; do
      yq -o=json "$yaml_file" 2>/dev/null |
        jq -r '.. | objects | to_entries[] | select(.key == "image" or (.key | endswith("_image"))) | .value | if type == "string" then . elif type == "object" and (.repository | type) == "string" then .repository + (if (.tag // "") == "" then "" else ":" + .tag end) else empty end' |
        while read -r image; do
          image_row "$image"
        done
    done
  } | sort -u
}

generate_table > "$TABLE_FILE"

# Build new README: before marker + marker + table + end marker + after marker
{
  sed -n '1,/<!-- DOCKER_SERVICES_START -->/p' "$README_FILE"
  cat "$TABLE_FILE"
  sed -n '/<!-- DOCKER_SERVICES_END -->/,$p' "$README_FILE"
} > "${README_FILE}.tmp" && mv "${README_FILE}.tmp" "$README_FILE"

echo "Updated ${README_FILE} with $(wc -l < "$TABLE_FILE" | tr -d ' ') lines (including header)"
