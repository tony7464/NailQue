# NailQue Production Readiness (macOS)

## Pre-Launch Checklist

- Build installer: `./build-mac.sh`
- Verify app routes:
  - `http://localhost:5001/`
  - `http://localhost:5001/employee`
  - `http://localhost:5001/api/health`
- Confirm runtime files in `~/Library/Application Support/NailQue`:
  - `manager_settings.json`
  - `logs/nailque.log`
- Confirm manager PIN behavior and tech management flows
- Confirm queue assignment, finish-service totals, and employee login

## Packaging Output

- Installer: `dist-installers/NailQue-macOS.pkg`
- App install path: `/Applications/NailQue.app`

## Clean Reinstall

```bash
rm -rf "/Applications/NailQue.app"
sudo installer -pkg "dist-installers/NailQue-macOS.pkg" -target /
open "/Applications/NailQue.app"
```
