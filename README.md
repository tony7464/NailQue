# NailQue

Salon queue, employee portal, and technician mobile app packaged as a desktop installer for macOS and Windows.

## Run from source

From the repo root (macOS helpers create `.venv` so packages are not installed into system Python):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=src python -m nailque
```

On a Mac you can also double-click `platforms/macos/start-dev.command`. That starts the app with auto-reload on `http://localhost:5001`.

Routes:

- Queue: `http://localhost:5001/`
- Employee portal: `http://localhost:5001/employee`
- Mobile portal: `http://<lan-ip>:5001/mobile`
- Health: `http://localhost:5001/api/health`

Copy `.env.example` to `.env` for local settings. Runtime JSON and logs are written next to the source tree when you run from source.

## Layout

- `src/nailque/` — Python app (Flask API, updater, desktop window)
- `web/` — queue, employee, and mobile pages
- `assets/` — icons, sounds, cursors
- `platforms/macos/` — Mac version file, PKG build, and local helpers
- `platforms/windows/` — Windows version file, EXE/Inno build
- `tools/` — PyInstaller wrapper, QA sweep, zip packaging
- `docs/installers.md` — installer, OTA, and production checklist

## Branch model

`main` holds the shared app plus both platform folders. Ship a platform by fast-forwarding the matching release branch from `main`:

- `release/macos` — GitHub Actions builds `NailQue-macOS-<version>.pkg` and publishes tag `v1.0.<run_number>`
- `release/windows` — GitHub Actions builds `NailQue-Setup-<version>.exe` and publishes tag `windows-v1.0.<run_number>` (not marked latest)

Do feature work on branches off `main`. Do not develop on the release branches.

## Ship an update

1. Merge the work into `main`.
2. Fast-forward the platform you want to ship:

```bash
git checkout release/macos
git merge --ff-only main
git push origin release/macos
```

Windows is the same with `release/windows`. The in-app updater looks through recent GitHub Releases and installs the newest asset for the running OS (`.pkg` on Mac, `.exe` on Windows).
