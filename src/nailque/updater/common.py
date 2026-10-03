import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from nailque.config import (
    APP_VERSION,
    AUTO_UPDATE_CHECK_INTERVAL_SECONDS,
    AUTO_UPDATE_ENABLED,
    AUTO_UPDATE_INCLUDE_PRERELEASE,
    AUTO_UPDATE_REPO,
    UPDATES_DIR,
)

LOGGER = logging.getLogger("nailque")
UPDATE_LOCK = threading.Lock()
UPDATE_STATE = {
    "current_version": APP_VERSION,
    "repo": AUTO_UPDATE_REPO,
    "enabled": AUTO_UPDATE_ENABLED and bool(AUTO_UPDATE_REPO),
    "checking": False,
    "available": False,
    "latest_version": APP_VERSION,
    "release_name": "",
    "release_notes": "",
    "asset_name": "",
    "asset_url": "",
    "downloaded_path": "",
    "downloaded_version": "",
    "last_checked": 0,
    "last_error": "",
}


def _platform_updater():
    if sys.platform.startswith("win"):
        from nailque.updater import windows as platform_updater
    else:
        from nailque.updater import macos as platform_updater
    return platform_updater


def normalize_version(value: str):
    cleaned = str(value or "").strip().lower()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    parts = []
    for piece in cleaned.split("."):
        if piece.isdigit():
            parts.append(int(piece))
        else:
            num = ""
            for char in piece:
                if char.isdigit():
                    num += char
                else:
                    break
            parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer_version(candidate: str, current: str) -> bool:
    return normalize_version(candidate) > normalize_version(current)


def extract_version_from_asset_name(asset_name: str) -> str:
    name = str(asset_name or "")
    match = re.search(r"(\d+\.\d+\.\d+)", name)
    if match:
        return match.group(1)
    return ""


def fetch_latest_release(repo: str):
    if not repo:
        raise ValueError("AUTO_UPDATE_REPO is not configured.")
    api_url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
    request_obj = Request(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "NailQue-Updater"})
    with urlopen(request_obj, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("No releases found.")
    platform_updater = _platform_updater()
    for release in payload:
        if release.get("draft"):
            continue
        if not AUTO_UPDATE_INCLUDE_PRERELEASE and release.get("prerelease"):
            continue
        asset = platform_updater.select_release_asset(release)
        if not asset:
            continue
        tag_name = str(release.get("tag_name") or "").strip()
        if not tag_name:
            continue
        asset_name = str(asset.get("name") or "")
        version = extract_version_from_asset_name(asset_name)
        if not version:
            version = extract_version_from_asset_name(tag_name)
        if not version:
            version = tag_name[1:] if tag_name.lower().startswith("v") else tag_name
        if not version:
            continue
        return {
            "version": version,
            "release_name": str(release.get("name") or tag_name),
            "release_notes": str(release.get("body") or ""),
            "asset_name": asset_name,
            "asset_url": str(asset.get("browser_download_url") or ""),
        }
    expected = platform_updater.expected_extension()
    raise RuntimeError(f"No {expected} asset found on recent releases.")


def download_update_asset(asset_name: str, asset_url: str, version: str) -> str:
    if not asset_url:
        raise RuntimeError("Update asset URL is missing.")
    platform_updater = _platform_updater()
    safe_name = platform_updater.safe_download_name(asset_name, version)
    target = UPDATES_DIR / safe_name
    temp_target = target.with_suffix(target.suffix + ".partial")
    request_obj = Request(asset_url, headers={"User-Agent": "NailQue-Updater"})
    with urlopen(request_obj, timeout=40) as response, temp_target.open("wb") as file:
        shutil.copyfileobj(response, file)
    os.replace(temp_target, target)
    return str(target)


def set_update_error(message: str):
    with UPDATE_LOCK:
        UPDATE_STATE["checking"] = False
        UPDATE_STATE["last_error"] = message
        UPDATE_STATE["last_checked"] = int(time.time())


def check_for_updates(download_if_available: bool = True):
    if not UPDATE_STATE["enabled"]:
        return
    with UPDATE_LOCK:
        if UPDATE_STATE["checking"]:
            return
        UPDATE_STATE["checking"] = True
        UPDATE_STATE["last_error"] = ""
    try:
        release = fetch_latest_release(UPDATE_STATE["repo"])
        with UPDATE_LOCK:
            UPDATE_STATE["latest_version"] = release["version"]
            UPDATE_STATE["release_name"] = release["release_name"]
            UPDATE_STATE["release_notes"] = release["release_notes"]
            UPDATE_STATE["asset_name"] = release["asset_name"]
            UPDATE_STATE["asset_url"] = release["asset_url"]
            UPDATE_STATE["available"] = is_newer_version(release["version"], APP_VERSION)
            UPDATE_STATE["last_checked"] = int(time.time())
            if UPDATE_STATE.get("downloaded_version") != release["version"]:
                UPDATE_STATE["downloaded_path"] = ""
                UPDATE_STATE["downloaded_version"] = ""
        if download_if_available and UPDATE_STATE["available"]:
            downloaded_path = download_update_asset(release["asset_name"], release["asset_url"], release["version"])
            with UPDATE_LOCK:
                UPDATE_STATE["downloaded_path"] = downloaded_path
                UPDATE_STATE["downloaded_version"] = release["version"]
    except (ValueError, RuntimeError, OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
        set_update_error(str(error))
        return
    with UPDATE_LOCK:
        UPDATE_STATE["checking"] = False


def background_update_loop():
    while True:
        check_for_updates(download_if_available=True)
        time.sleep(AUTO_UPDATE_CHECK_INTERVAL_SECONDS)


def launch_background_updater():
    if not UPDATE_STATE["enabled"]:
        LOGGER.info("Auto-updater disabled. Set AUTO_UPDATE_REPO to enable OTA updates.")
        return
    thread = threading.Thread(target=background_update_loop, daemon=True)
    thread.start()
    LOGGER.info("Background auto-updater enabled for repo %s", UPDATE_STATE["repo"])


def get_update_status():
    with UPDATE_LOCK:
        return dict(UPDATE_STATE)


def install_downloaded_update():
    status = get_update_status()
    installer_path = status.get("downloaded_path") or ""
    if not installer_path or not Path(installer_path).exists():
        raise RuntimeError("No downloaded update package available.")
    latest_version = str(status.get("latest_version") or "").strip()
    downloaded_version = str(status.get("downloaded_version") or "").strip()
    if latest_version and downloaded_version and latest_version != downloaded_version:
        raise RuntimeError("Downloaded package is outdated. Run CHECK UPDATES first.")
    _platform_updater().install_update(installer_path)
