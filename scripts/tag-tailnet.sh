#!/usr/bin/env bash
# tag-tailnet.sh — Tag all devices that run Pangolin reverse-proxy sidecars
set -euo pipefail

TAG="tag:pangolin"
TS_NET=""
TS_API_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
  --ts-net)
    TS_NET="$2"
    shift 2
    ;;
  --ts-api-key)
    TS_API_KEY="$2"
    shift 2
    ;;
  *)
    echo "Unknown arg: $1"
    exit 1
    ;;
  esac
done

if [[ -z "$TS_NET" || -z "$TS_API_KEY" ]]; then
  echo "Usage: $0 --ts-net <tailnet> --ts-api-key <key>"
  exit 1
fi

# Services that use Pangolin sidecars
SERVICES=(
  audiobookshelf
  # bento-pdf
  # dispatcharr
  # forgejo
  # gotify
  # igotify
  # invidious
  # jellyfin
  # miniflux
  # navidrome
  # paperless-ngx
  # rfd-fyi
  # searxng
  # umami
  # vikunja
)

FAILED=0

for name in "${SERVICES[@]}"; do
  echo "Fetching device id for $name"
  id=$(curl -s -u "${TS_API_KEY}:" \
    "https://api.tailscale.com/api/v2/tailnet/${TS_NET}/devices" |
    jq -r --arg n "$name" '.devices[] | select(.hostname == $n) | .id')

  if [[ -z "$id" || "$id" == "null" ]]; then
    echo "  ✗ $name → device not found"
    FAILED=$((FAILED + 1))
    continue
  fi

  current_tags=$(curl -s -u "${TS_API_KEY}:" \
    "https://api.tailscale.com/api/v2/device/${id}" |
    jq -c '.tags // []')

  new_tags=$(jq -n --arg tag "$TAG" --argjson cur "$current_tags" \
    '[$cur[], $tag]  | unique')

  http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -u "${TS_API_KEY}:" \
    -H "Content-Type: application/json" \
    --data-binary "{\"tags\": $new_tags}" \
    "https://api.tailscale.com/api/v2/device/${id}/tags")

  if [[ "$http_code" == "200" ]]; then
    echo "  ✓ $name ($id) → $TAG"
  else
    echo "  ✗ $name ($id) → HTTP $http_code"
    FAILED=$((FAILED + 1))
  fi

done

echo ""
if [[ $FAILED -eq 0 ]]; then
  echo "All tagged successfully."
else
  echo "$FAILED device(s) failed."
fi
