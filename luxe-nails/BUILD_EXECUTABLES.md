# Build macOS Installer

This project is now streamlined for macOS distribution.

## One-command build

From the `luxe-nails` folder:

```bash
chmod +x build-mac.sh
./build-mac.sh
```

Build + reinstall latest automatically:

```bash
AUTO_INSTALL=true ./build-mac.sh
```

One-command helper:

```bash
chmod +x update-mac.command
./update-mac.command
```

Output:
- `dist-installers/NailQue-macOS-<version>.pkg`
- `dist-installers/NailQue-macOS.pkg` (latest alias)

Versioning:
- Installer/app version is read from `VERSION`.
- To release a new OTA update, bump `VERSION`, build, then publish the generated `.pkg` asset to a GitHub release with matching tag (example: `v1.0.5`).
- You can still override at build time: `PKG_VERSION=1.0.5 ./build-mac.sh`

## Optional icon (recommended)

Add this file before building:
- `assets/icons/app.icns`

If present, it is embedded in the app bundle automatically.

## Source run helper

Use `start-mac.command` to run from source without packaging.
It now runs in dev-reload mode, so saving source files automatically reloads the app for testing.

## Runtime behavior

After install, the app lives at:
- `/Applications/NailQue.app`

The app serves:
- Queue screen: `http://localhost:5001/`
- Employee portal: `http://localhost:5001/employee`

Runtime files are stored in:
- `~/Library/Application Support/NailQue`

## OTA updater (GitHub Releases)

Configure in runtime `.env`:

```bash
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_REPO=owner/repo
AUTO_UPDATE_CHECK_INTERVAL_SECONDS=900
AUTO_UPDATE_INCLUDE_PRERELEASE=false
```

The app checks in the background, downloads the latest `.pkg` release asset automatically, and exposes install controls in Tech Management.
