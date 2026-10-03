#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
chmod +x ./build-installer.sh
./build-installer.sh

ROOT_DIR="$(cd ../.. && pwd)"
if [[ "${AUTO_INSTALL:-false}" == "true" ]]; then
  echo ""
  echo "==> Installing latest macOS package"
  PKG_PATH="$ROOT_DIR/dist-installers/NailQue-macOS.pkg"
  if [[ ! -f "$PKG_PATH" ]]; then
    echo "Expected installer not found at $PKG_PATH"
    exit 1
  fi
  pkill -x "NailQue" >/dev/null 2>&1 || true
  sudo installer -pkg "$PKG_PATH" -target /
  open "/Applications/NailQue.app"
  echo "Auto-install complete."
fi

echo ""
echo "macOS installer build finished. Check $ROOT_DIR/dist-installers/NailQue-macOS.pkg"
echo "Tip: AUTO_INSTALL=true ./build.sh"
