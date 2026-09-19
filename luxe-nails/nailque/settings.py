"""Environment-backed application settings."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_app_version(assets_dir: Path) -> str:
    if sys.platform.startswith("win"):
        version_files = [assets_dir / "VERSION.windows", assets_dir / "VERSION"]
    elif sys.platform == "darwin":
        version_files = [assets_dir / "VERSION.macos", assets_dir / "VERSION"]
    else:
        version_files = [assets_dir / "VERSION"]
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


def load_or_create_secret_key(secret_key_file: Path) -> str:
    env_key = (os.getenv("SECRET_KEY") or "").strip()
    if env_key:
        return env_key
    if secret_key_file.exists():
        stored = secret_key_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    generated = secrets.token_hex(32)
    secret_key_file.write_text(generated, encoding="utf-8")
    try:
        os.chmod(secret_key_file, 0o600)
    except OSError:
        pass
    return generated


class Settings:
    def __init__(self, assets_dir: Path, secret_key_file: Path):
        self.app_version = load_app_version(assets_dir)
        self.is_windows = sys.platform.startswith("win")
        self.is_frozen = bool(getattr(sys, "frozen", False))
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "5001"))
        self.auto_open_browser = env_flag("AUTO_OPEN_BROWSER", True)
        self.use_desktop_window = env_flag("USE_DESKTOP_WINDOW", True)
        self.dev_reload = env_flag("DEV_RELOAD", False) and not self.is_frozen
        self.trust_proxy = env_flag("TRUST_PROXY", False)
        self.secret_key = load_or_create_secret_key(secret_key_file)
        self.manager_full_name = (os.getenv("MANAGER_FULL_NAME", "Admin") or "Admin").strip() or "Admin"
        self.manager_username = (os.getenv("MANAGER_USERNAME", "admin") or "admin").strip().lower() or "admin"
        self.manager_pin = (os.getenv("MANAGER_PIN", "1234") or "1234").strip() or "1234"
        default_repo = "tony7464/NailQue"
        repo_env = (os.getenv("AUTO_UPDATE_REPO") or "").strip()
        self.auto_update_repo = repo_env or default_repo
        self.auto_update_enabled = env_flag("AUTO_UPDATE_ENABLED", True) and bool(self.auto_update_repo)
        self.auto_update_check_interval_seconds = max(300, int(os.getenv("AUTO_UPDATE_CHECK_INTERVAL_SECONDS", "900")))
        self.auto_update_include_prerelease = env_flag("AUTO_UPDATE_INCLUDE_PRERELEASE", False)
        self.mobile_session_ttl_seconds = 12 * 60 * 60
        self.manager_session_ttl_seconds = 8 * 60 * 60
        self.employee_session_ttl_seconds = 12 * 60 * 60
        self.max_content_length = 64 * 1024
