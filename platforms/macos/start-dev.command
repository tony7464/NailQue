#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"
if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi
PYTHON="$ROOT_DIR/.venv/bin/python"
"$PYTHON" -m pip install -r requirements.txt
export PYTHONPATH="$ROOT_DIR/src"
export USE_DESKTOP_WINDOW=false
export DEV_RELOAD=true
export AUTO_OPEN_BROWSER=true
"$PYTHON" -m nailque
