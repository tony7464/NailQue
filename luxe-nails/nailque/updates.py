"""GitHub-release over-the-air updater."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ALLOWED_UPDATE_HOSTS = {
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
}


def normalize_version(value: str) -> tuple[int, int, int]:
    cleaned = str(value or "").strip().lower()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    parts = []
    for piece in cleaned.split("."):
        if piece.isdigit():
            parts.append(int(piece))
            continue
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer_version(candidate: str, current: str) -> bool:
    return normalize_version(candidate) > normalize_version(current)


def extract_version_from_asset_name(asset_name: str) -> str:
    match = re.search(r"(\d+\.\d+\.\d+)", str(asset_name or ""))
    return match.group(1) if match else ""


def assert_https_github_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_UPDATE_HOSTS:
        raise RuntimeError("Update URL is not from an allowed GitHub host.")


def select_release_asset(release_payload: dict, is_windows: bool) -> dict | None:
    assets = release_payload.get("assets") or []
    preferred_extensions = [".exe"] if is_windows else [".pkg"]
    preferred_name_hints = ["NailQue-Setup", "NailQue-Windows", "NailQue"] if is_windows else ["NailQue-macOS"]
    for asset in assets:
        name = str(asset.get("name") or "")
        if any(name.endswith(ext) for ext in preferred_extensions) and any(hint in name for hint in preferred_name_hints):
            return asset
    for asset in assets:
        name = str(asset.get("name") or "")
        if any(name.endswith(ext) for ext in preferred_extensions):
            return asset
    return None


class Updater:
    def __init__(self, settings, updates_dir: Path, logger):
        self.settings = settings
        self.updates_dir = updates_dir
        self.logger = logger
        self.lock = threading.Lock()
        self.state = {
            "current_version": settings.app_version,
            "repo": settings.auto_update_repo,
            "enabled": settings.auto_update_enabled,
            "checking": False,
            "available": False,
            "latest_version": settings.app_version,
            "release_name": "",
            "release_notes": "",
            "asset_name": "",
            "asset_url": "",
            "downloaded_path": "",
            "downloaded_version": "",
            "last_checked": 0,
            "last_error": "",
        }

    def snapshot(self, public: bool = True) -> dict:
        with self.lock:
            data = dict(self.state)
        if public:
            data["package_ready"] = bool(data.get("downloaded_path"))
            data["downloaded_path"] = ""
        else:
            data["package_ready"] = bool(data.get("downloaded_path"))
        return data

    def _set_error(self, message: str) -> None:
        with self.lock:
            self.state["checking"] = False
            self.state["last_error"] = message
            self.state["last_checked"] = int(time.time())

    def _fetch_latest_release(self) -> dict:
        repo = self.settings.auto_update_repo
        if not repo:
            raise ValueError("AUTO_UPDATE_REPO is not configured.")
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        if self.settings.auto_update_include_prerelease:
            api_url = f"https://api.github.com/repos/{repo}/releases?per_page=8"
        assert_https_github_url(api_url)
        request_obj = Request(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "NailQue-Updater"})
        with urlopen(request_obj, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if self.settings.auto_update_include_prerelease:
            if not isinstance(payload, list) or not payload:
                raise RuntimeError("No releases found.")
            release = payload[0]
        else:
            release = payload
        tag_name = str(release.get("tag_name") or "").strip()
        if not tag_name:
            raise RuntimeError("Latest release is missing tag_name.")
        asset = select_release_asset(release, self.settings.is_windows)
        if not asset:
            expected = ".exe" if self.settings.is_windows else ".pkg"
            raise RuntimeError(f"No {expected} asset found on latest release.")
        asset_name = str(asset.get("name") or "")
        asset_url = str(asset.get("browser_download_url") or "")
        assert_https_github_url(asset_url)
        version = extract_version_from_asset_name(asset_name)
        if not version:
            version = tag_name[1:] if tag_name.lower().startswith("v") else tag_name
        return {
            "version": version,
            "release_name": str(release.get("name") or tag_name),
            "release_notes": str(release.get("body") or ""),
            "asset_name": asset_name,
            "asset_url": asset_url,
        }

    def _download_update_asset(self, asset_name: str, asset_url: str, version: str) -> str:
        assert_https_github_url(asset_url)
        safe_name = f"NailQue-Setup-{version}.exe" if self.settings.is_windows else f"NailQue-macOS-{version}.pkg"
        if (self.settings.is_windows and asset_name.endswith(".exe")) or ((not self.settings.is_windows) and asset_name.endswith(".pkg")):
            safe_name = Path(asset_name).name
        if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
            raise RuntimeError("Update asset name is invalid.")
        target = self.updates_dir / safe_name
        temp_target = target.with_suffix(target.suffix + ".partial")
        request_obj = Request(asset_url, headers={"User-Agent": "NailQue-Updater"})
        with urlopen(request_obj, timeout=40) as response, temp_target.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        os.replace(temp_target, target)
        return str(target)

    def check(self, download_if_available: bool = True) -> None:
        if not self.state["enabled"]:
            return
        with self.lock:
            if self.state["checking"]:
                return
            self.state["checking"] = True
            self.state["last_error"] = ""
        try:
            release = self._fetch_latest_release()
            with self.lock:
                self.state["latest_version"] = release["version"]
                self.state["release_name"] = release["release_name"]
                self.state["release_notes"] = release["release_notes"]
                self.state["asset_name"] = release["asset_name"]
                self.state["asset_url"] = release["asset_url"]
                self.state["available"] = is_newer_version(release["version"], self.settings.app_version)
                self.state["last_checked"] = int(time.time())
                if self.state.get("downloaded_version") != release["version"]:
                    self.state["downloaded_path"] = ""
                    self.state["downloaded_version"] = ""
            if download_if_available and self.state["available"]:
                downloaded_path = self._download_update_asset(release["asset_name"], release["asset_url"], release["version"])
                with self.lock:
                    self.state["downloaded_path"] = downloaded_path
                    self.state["downloaded_version"] = release["version"]
        except (ValueError, RuntimeError, OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
            self._set_error(str(error))
            return
        with self.lock:
            self.state["checking"] = False

    def start_background_loop(self) -> None:
        if not self.state["enabled"]:
            self.logger.info("Auto-updater disabled. Set AUTO_UPDATE_REPO to enable OTA updates.")
            return

        def loop():
            while True:
                self.check(download_if_available=True)
                time.sleep(self.settings.auto_update_check_interval_seconds)

        threading.Thread(target=loop, daemon=True).start()
        self.logger.info("Background auto-updater enabled for repo %s", self.state["repo"])

    def _validated_installer(self) -> Path:
        status = self.snapshot(public=False)
        installer_path = status.get("downloaded_path") or ""
        if not installer_path:
            raise RuntimeError("No downloaded update package available.")
        path = Path(installer_path).resolve()
        updates_root = self.updates_dir.resolve()
        try:
            path.relative_to(updates_root)
        except ValueError as error:
            raise RuntimeError("Installer path is not in the updates directory.") from error
        allowed_suffix = ".exe" if self.settings.is_windows else ".pkg"
        if path.suffix.lower() != allowed_suffix:
            raise RuntimeError("Installer file type is not allowed.")
        if not path.is_file():
            raise RuntimeError("No downloaded update package available.")
        latest_version = str(status.get("latest_version") or "").strip()
        downloaded_version = str(status.get("downloaded_version") or "").strip()
        if latest_version and downloaded_version and latest_version != downloaded_version:
            raise RuntimeError("Downloaded package is outdated. Run CHECK UPDATES first.")
        return path

    def install(self) -> None:
        installer_path = self._validated_installer()
        if self.settings.is_windows:
            launch_candidate = str(Path(sys.executable)) if getattr(sys, "frozen", False) else ""
            launch_fallback = str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NailQue" / "NailQue.exe")
            command = (
                "Start-Process -FilePath $env:NAILQUE_INSTALLER "
                "-ArgumentList '/VERYSILENT','/NORESTART','/CLOSEAPPLICATIONS' -Verb RunAs -Wait; "
                "if ($env:NAILQUE_LAUNCH -and (Test-Path $env:NAILQUE_LAUNCH)) { Start-Process -FilePath $env:NAILQUE_LAUNCH } "
                "elseif (Test-Path $env:NAILQUE_LAUNCH_FALLBACK) { Start-Process -FilePath $env:NAILQUE_LAUNCH_FALLBACK }"
            )
            env = os.environ.copy()
            env["NAILQUE_INSTALLER"] = str(installer_path)
            env["NAILQUE_LAUNCH"] = launch_candidate
            env["NAILQUE_LAUNCH_FALLBACK"] = launch_fallback
            process = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        else:
            process = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'on run argv',
                    "-e",
                    "set installerPath to item 1 of argv",
                    "-e",
                    'do shell script "installer -pkg " & quoted form of installerPath & " -target / && (pkill -x NailQue || true) && (pkill -f \\"/Applications/NailQue.app/Contents/MacOS/NailQue\\" || true) && sleep 1 && open -n \\"/Applications/NailQue.app\\"" with administrator privileges',
                    "-e",
                    "end run",
                    str(installer_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        if process.returncode != 0:
            stderr = (process.stderr or "").strip() or "Update installation failed."
            raise RuntimeError(stderr)
