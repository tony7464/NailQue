# Installer Guide

Full product overview, security notes, and screenshots live in the [root README](../README.md).

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

- `dist-installers/NailQue-macOS-<version>.pkg`
- `dist-installers/NailQue-macOS.pkg` (latest alias)

Version comes from `VERSION`. Override with `PKG_VERSION=3.1.0 ./build-mac.sh`.

Auto-reinstall after build:

```bash
AUTO_INSTALL=true ./build-mac.sh
```

Or run `./update-mac.command`.

## Install on a Mac

1. Double-click `NailQue-macOS.pkg`
2. Complete the installer prompts
3. Launch NailQue from Applications (`/Applications/NailQue.app`)

Runtime files: `~/Library/Application Support/NailQue`

## Source run (no installer)

```bash
chmod +x start-mac.command
./start-mac.command
```

## OTA updater

Set these in the runtime `.env`:

```bash
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_REPO=owner/repo
AUTO_UPDATE_CHECK_INTERVAL_SECONDS=900
AUTO_UPDATE_INCLUDE_PRERELEASE=false
```

Release flow:

1. Bump `VERSION`
2. Build the pkg
3. Publish it on a GitHub Release with a matching tag (`v3.1.0`)
4. A signed-in manager can check and install from Tech Management

## Windows installer

On a Windows build machine:

```powershell
.\build-windows.ps1
```

Requirements: Python 3.10+ and Inno Setup 6. Details are in [installers/windows/README.md](installers/windows/README.md).
