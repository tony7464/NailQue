"""Runtime and asset path resolution for source and packaged builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def detect_asset_and_runtime_dirs() -> tuple[Path, Path]:
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
        assets_dir = Path(__file__).resolve().parent.parent
        runtime_dir = assets_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return assets_dir, runtime_dir


def load_environment(assets_dir: Path, runtime_dir: Path) -> None:
    """Load env files. Later sources override earlier ones."""
    load_dotenv(assets_dir / ".env", override=False)
    load_dotenv(runtime_dir / ".env", override=True)
    env_override = (os.environ.get("NAILQUE_ENV_FILE") or "").strip()
    if not env_override:
        return
    override_path = Path(env_override).expanduser()
    if override_path.is_file():
        load_dotenv(override_path, override=True)


class AppPaths:
    def __init__(self, assets_dir: Path | None = None, runtime_dir: Path | None = None):
        detected_assets, detected_runtime = detect_asset_and_runtime_dirs()
        self.assets_dir = assets_dir or detected_assets
        self.runtime_dir = runtime_dir or detected_runtime
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.runtime_dir / "logs"
        self.updates_dir = self.runtime_dir / "updates"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.updates_dir.mkdir(parents=True, exist_ok=True)
        self.manager_settings_file = self.runtime_dir / "manager_settings.json"
        self.shared_state_file = self.runtime_dir / "shared_state.json"
        self.service_history_file = self.runtime_dir / "service_history.json"
        self.manager_activity_file = self.runtime_dir / "manager_activity_log.json"
        self.secret_key_file = self.runtime_dir / "secret_key"
        self.static_dir = self.assets_dir / "static"
        self.assets_public_dir = self.assets_dir / "assets"

    def page_file(self, name: str) -> Path:
        return self.assets_dir / name
