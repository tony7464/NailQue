import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _get_paths():
    if getattr(sys, "frozen", False):
        assets_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        if sys.platform.startswith("win"):
            runtime_root = os.environ.get("APPDATA") or str(Path.home())
            runtime_dir = Path(runtime_root) / "NailQue"
        elif sys.platform == "darwin":
            runtime_dir = Path.home() / "Library" / "Application Support" / "NailQue"
        else:
            runtime_dir = Path.home() / ".config" / "NailQue"
    else:
        assets_dir = Path(__file__).resolve().parents[2]
        runtime_dir = assets_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return assets_dir, runtime_dir


ASSETS_DIR, RUNTIME_DIR = _get_paths()
WEB_DIR = ASSETS_DIR / "web"
# Env load order (later wins):
# 1) Bundled / repo: ASSETS_DIR/.env — when running from source this is the repo root.
# 2) Installed app data:
#    - macOS: ~/Library/Application Support/NailQue/.env
#    - Windows: %APPDATA%/NailQue/.env
#    - Linux: ~/.config/NailQue/.env
# 3) Optional absolute path: set NAILQUE_ENV_FILE so the installed app uses a specific file.
load_dotenv(ASSETS_DIR / ".env", override=False)
load_dotenv(RUNTIME_DIR / ".env", override=True)
_env_override = (os.environ.get("NAILQUE_ENV_FILE") or "").strip()
if _env_override:
    _p = Path(_env_override).expanduser()
    if _p.is_file():
        load_dotenv(_p, override=True)

MANAGER_SETTINGS_FILE = RUNTIME_DIR / "manager_settings.json"
LOGS_DIR = RUNTIME_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
UPDATES_DIR = RUNTIME_DIR / "updates"
UPDATES_DIR.mkdir(parents=True, exist_ok=True)
SHARED_STATE_FILE = RUNTIME_DIR / "shared_state.json"
SERVICE_HISTORY_FILE = RUNTIME_DIR / "service_history.json"
MANAGER_ACTIVITY_FILE = RUNTIME_DIR / "manager_activity_log.json"


def _load_app_version() -> str:
    version_files = [ASSETS_DIR / "VERSION"]
    if not getattr(sys, "frozen", False):
        platform_name = "windows" if sys.platform.startswith("win") else "macos"
        version_files.append(ASSETS_DIR / "platforms" / platform_name / "VERSION")
    for version_file in version_files:
        if not version_file.exists():
            continue
        try:
            version = version_file.read_text(encoding="utf-8").strip()
            if version:
                return version
        except OSError:
            continue
    return "1.0.0"


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


APP_VERSION = _load_app_version()
IS_WINDOWS = sys.platform.startswith("win")
_DEFAULT_UPDATE_REPO = "tony7464/NailQue"
_repo_env = (os.getenv("AUTO_UPDATE_REPO") or "").strip()
AUTO_UPDATE_REPO = _repo_env or _DEFAULT_UPDATE_REPO
AUTO_UPDATE_ENABLED = os.getenv("AUTO_UPDATE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
AUTO_UPDATE_CHECK_INTERVAL_SECONDS = max(300, int(os.getenv("AUTO_UPDATE_CHECK_INTERVAL_SECONDS", "900")))
AUTO_UPDATE_INCLUDE_PRERELEASE = os.getenv("AUTO_UPDATE_INCLUDE_PRERELEASE", "false").strip().lower() in {"1", "true", "yes", "on"}
