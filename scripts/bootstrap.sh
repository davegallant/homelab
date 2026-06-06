#!/usr/bin/env bash
set -euo pipefail

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
DEBIAN_FRONTEND=noninteractive apt-get install -y curl
curl -fsSL https://tailscale.com/install.sh | sh
