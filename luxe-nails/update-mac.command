#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
chmod +x ./build-mac.sh
AUTO_INSTALL=true ./build-mac.sh
