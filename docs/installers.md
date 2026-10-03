# Installer guide

## Platform support

- macOS: PKG installer pipeline
- Windows: standalone EXE zip + setup installer EXE pipeline

## Build macOS installer

From the repo root, or from `platforms/macos`:

```bash
chmod +x platforms/macos/build.sh
./platforms/macos/build.sh
```

Installer output:

- `dist-installers/NailQue-macOS-<version>.pkg` (unique build artifact)
- `dist-installers/NailQue-macOS.pkg` (latest alias)

Versioning:

- Installer/app version is read from `platforms/macos/VERSION`
- Optional override: `PKG_VERSION=1.0.5 ./platforms/macos/build.sh`

Auto reinstall after build:

```bash
AUTO_INSTALL=true ./platforms/macos/build.sh
```

Or run the helper:

```bash
chmod +x platforms/macos/reinstall.command
./platforms/macos/reinstall.command
```

## Install on a Mac

1. Double-click `NailQue-macOS.pkg`
2. Complete the installer prompts
3. Launch `NailQue` from Applications

Installed app path: `/Applications/NailQue.app`

Runtime files are stored in `~/Library/Application Support/NailQue`.

## Fast local testing (no pkg reinstall)

```bash
chmod +x platforms/macos/start-dev.command
./platforms/macos/start-dev.command
```

This runs from source with auto-reload enabled.

## Optional icon

Add `assets/icons/app.icns` before building. If present, it is embedded in the app bundle.

On Windows, `assets/icons/app.ico` is used when present; otherwise a PNG is converted to ICO at build time.

## OTA updater (GitHub Releases)

Set these values in the runtime `.env` (inside the app support folder or the source folder):

```bash
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_REPO=tony7464/NailQue
AUTO_UPDATE_CHECK_INTERVAL_SECONDS=900
AUTO_UPDATE_INCLUDE_PRERELEASE=false
```

Release flow:

1. Merge the work into `main`
2. Fast-forward and push `release/macos` or `release/windows`
3. CI publishes the platform installer as a GitHub Release asset
4. Installed clients detect, download, and offer install from Tech Management

The updater lists recent GitHub Releases and uses the newest asset for the running OS, so a Windows release is never installed on a Mac client.

## Clean reinstall (macOS)

```bash
rm -rf "/Applications/NailQue.app"
sudo installer -pkg "dist-installers/NailQue-macOS.pkg" -target /
open "/Applications/NailQue.app"
```

## Build Windows installer

From `platforms/windows` on a Windows build machine:

```powershell
.\build.ps1
```

Or double-click `build.bat`.

Generated artifacts:

- `dist-installers/NailQue-Windows-Standalone-<version>.zip`
- `dist-installers/NailQue-Setup-<version>.exe`
- `dist-installers/NailQue-Setup.exe` (latest alias)

Requirements:

- Python 3.10+
- Inno Setup 6 installed, or `INNO_SETUP_ISCC` set to `ISCC.exe`

Versioning: Windows uses `platforms/windows/VERSION`.

Installed app default path: `C:\Program Files\NailQue\NailQue.exe`

Runtime state and logs: `%APPDATA%\NailQue`

## Production checklist

- Build the installer for the target OS
- Verify app routes:
  - `http://localhost:5001/`
  - `http://localhost:5001/employee`
  - `http://localhost:5001/api/health`
- Confirm runtime files (`manager_settings.json`, `logs/nailque.log`)
- Confirm manager PIN behavior and tech management flows
- Confirm queue assignment, finish-service totals, and employee login
