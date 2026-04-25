#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
OUT_DIR="$ROOT_DIR/dist-installers"
WORK_BASE="$ROOT_DIR/installer-work/macos"
APP_NAME="NailQue"
VERSION_FILE="$ROOT_DIR/VERSION"
if [[ -f "$VERSION_FILE" ]]; then
  DEFAULT_VERSION="$(tr -d ' \t\r\n' < "$VERSION_FILE")"
else
  DEFAULT_VERSION=""
fi
APP_VERSION="${PKG_VERSION:-$DEFAULT_VERSION}"
if [[ -z "$APP_VERSION" ]]; then
  echo "Missing version. Set PKG_VERSION or create $VERSION_FILE."
  exit 1
fi

echo "==> Building one-file executable"
cd "$ROOT_DIR"
python3 -m pip install -r requirements.txt
python3 build_executable.py

if [[ ! -f "$DIST_DIR/$APP_NAME" ]]; then
  echo "Expected executable not found at $DIST_DIR/$APP_NAME"
  exit 1
fi

echo "==> Preparing macOS app bundle"
mkdir -p "$WORK_BASE" "$OUT_DIR"
WORK_DIR="$(mktemp -d "$WORK_BASE/build.XXXXXX")"
APP_BUNDLE="$WORK_DIR/payload/Applications/${APP_NAME}.app"
APP_EXEC="$APP_BUNDLE/Contents/MacOS/${APP_NAME}"
APP_INFO="$APP_BUNDLE/Contents/Info.plist"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

cp "$DIST_DIR/$APP_NAME" "$APP_EXEC"
chmod +x "$APP_EXEC"

ICON_FILE="$ROOT_DIR/assets/icons/app.icns"
ICON_NAME=""
if [[ -f "$ICON_FILE" ]]; then
  ICON_NAME="app.icns"
  cp "$ICON_FILE" "$APP_BUNDLE/Contents/Resources/$ICON_NAME"
fi

cat > "$APP_INFO" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>com.mvince.nailque</string>
  <key>CFBundleVersion</key>
  <string>${APP_VERSION}</string>
  <key>CFBundleShortVersionString</key>
  <string>${APP_VERSION}</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
EOF

if [[ -n "$ICON_NAME" ]]; then
cat >> "$APP_INFO" <<EOF
  <key>CFBundleIconFile</key>
  <string>${ICON_NAME}</string>
EOF
fi

cat >> "$APP_INFO" <<EOF
</dict>
</plist>
EOF

PKG_PATH="$OUT_DIR/NailQue-macOS.pkg"
echo "==> Building PKG installer"
rm -f "$PKG_PATH"
pkgbuild \
  --root "$WORK_DIR/payload" \
  --identifier "com.mvince.nailque" \
  --version "$APP_VERSION" \
  --install-location "/" \
  "$PKG_PATH"

echo ""
echo "Installer created:"
echo "  $PKG_PATH"
echo "Version:"
echo "  $APP_VERSION"
