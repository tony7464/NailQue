# NailQue Windows Install Bundle

This folder contains only the files needed to run NailQue on Windows.

## Included runtime files

- `app.py`
- `luxe-nails-queue.html`
- `luxe-nails-employee.html`
- `luxe-nails-mobile.html`
- `assets/`
- `requirements-windows.txt`
- `Install-NailQue-Windows.bat`
- `Start-NailQue.bat`

## Install on Windows (clickable)

1. Open this folder on the Windows machine.
2. Double-click `Install-NailQue-Windows.bat`.
3. After installation, double-click `Start-NailQue.bat` (or the desktop shortcut `NailQue`).

## Build a classic Windows installer (.exe)

1. On a Windows machine, install Inno Setup 6: https://jrsoftware.org/isdl.php
2. Open this folder.
3. Double-click `Build-Windows-Installer.bat`.
4. When complete, share/use:
   - `dist-installers/NailQue-Setup.exe`

## Notes

- This bundle contains only Windows runtime/install files.
- `sync_windows_bundle.py` is used during install/build to refresh this folder from the latest root project files.
- If Python is not installed, the installer will prompt you to install Python 3.10+ first.
