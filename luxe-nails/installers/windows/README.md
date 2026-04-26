# Windows Installer Guide

This project supports a dedicated Windows release pipeline that produces:

- A standalone executable zip:
  - `dist-installers/NailQue-Windows-Standalone-<version>.zip`
- A full Windows installer:
  - `dist-installers/NailQue-Setup-<version>.exe`
  - `dist-installers/NailQue-Setup.exe` (latest alias)

## Requirements (Windows build machine)

1. Python 3.10+
2. Inno Setup 6 (`ISCC.exe`)
   - Install from [https://jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)
   - Or set `INNO_SETUP_ISCC` to your `ISCC.exe` path

## One-command build

From the `luxe-nails` folder on Windows:

```powershell
.\build-windows.ps1
```

Or double-click:

```text
build-windows.bat
```

## Runtime behavior

- Installed app default path: `C:\Program Files\NailQue\NailQue.exe`
- Runtime state and logs: `%APPDATA%\NailQue`

## OTA release assets

For Windows clients, publish a Windows installer `.exe` release asset (recommended naming: `NailQue-Setup-<version>.exe`).
The in-app updater on Windows will prefer `.exe` installer assets and run them with elevation.
