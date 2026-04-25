#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
export USE_DESKTOP_WINDOW=false
export DEV_RELOAD=true
export AUTO_OPEN_BROWSER=true
python3 app.py
