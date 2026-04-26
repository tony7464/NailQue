# Installer Guide

## Platform support

- macOS: PKG installer pipeline
- Windows: standalone EXE zip + setup installer EXE pipeline

## Build macOS installer

From `luxe-nails`:

```bash
chmod +x build-mac.sh
./build-mac.sh
```

Installer output:
- `dist-installers/NailQue-macOS-<version>.pkg` (unique build artifact)
- `dist-installers/NailQue-macOS.pkg` (latest alias)

Installer versioning:
- Installer/app version is read from `VERSION`
- Optional override: `PKG_VERSION=1.0.5 ./build-mac.sh`

Auto reinstall after build:

```bash
AUTO_INSTALL=true ./build-mac.sh
```

Or run one command helper:

```bash
chmod +x update-mac.command
./update-mac.command
```

## Install on a Mac

1. Double-click `NailQue-macOS.pkg`
2. Complete the installer prompts
3. Launch `NailQue` from Applications

Installed app path:
- `/Applications/NailQue.app`

## Fast local testing (no pkg reinstall)

From `luxe-nails`:

```bash
chmod +x start-mac.command
./start-mac.command
```

This runs from source with auto-reload enabled, so file saves are picked up automatically during testing.

## OTA updater (GitHub Releases)

Set these values in the runtime `.env` (inside app support folder or source folder):

```bash
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_REPO=owner/repo
AUTO_UPDATE_CHECK_INTERVAL_SECONDS=900
AUTO_UPDATE_INCLUDE_PRERELEASE=false
```

Release flow for over-the-air updates:
1. Bump `VERSION`
2. Build pkg (`./build-mac.sh`)
3. Publish the generated `.pkg` as a GitHub Release asset with a matching tag (example: `v1.0.5`)
4. Installed clients will detect, download, and offer install from Tech Management

## Clean reinstall (if needed)

If you had prior broken installs:

```bash
rm -rf "/Applications/NailQue.app"
sudo installer -pkg "dist-installers/NailQue-macOS.pkg" -target /
open "/Applications/NailQue.app"
```

## Build Windows installer

From `luxe-nails` on a Windows build machine:

```powershell
.\build-windows.ps1
```

Or double-click:

```text
build-windows.bat
```

Generated artifacts:
- `dist-installers/NailQue-Windows-Standalone-<version>.zip`
- `dist-installers/NailQue-Setup-<version>.exe`
- `dist-installers/NailQue-Setup.exe` (latest alias)

Requirements:
- Python 3.10+
- Inno Setup 6 installed, or `INNO_SETUP_ISCC` set to `ISCC.exe`

Versioning:
- macOS uses `VERSION`
- Windows uses `VERSION.windows` (falls back to `VERSION` if missing)
