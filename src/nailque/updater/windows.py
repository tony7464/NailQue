import os
import subprocess
import sys
from pathlib import Path


PREFERRED_EXTENSIONS = [".exe"]
PREFERRED_NAME_HINTS = ["NailQue-Setup", "NailQue-Windows", "NailQue"]


def select_release_asset(release_payload):
    assets = release_payload.get("assets") or []
    for asset in assets:
        name = str(asset.get("name") or "")
        if any(name.endswith(ext) for ext in PREFERRED_EXTENSIONS) and any(hint in name for hint in PREFERRED_NAME_HINTS):
            return asset
    for asset in assets:
        name = str(asset.get("name") or "")
        if any(name.endswith(ext) for ext in PREFERRED_EXTENSIONS):
            return asset
    return None


def expected_extension() -> str:
    return ".exe"


def safe_download_name(asset_name: str, version: str) -> str:
    if asset_name.endswith(".exe"):
        return asset_name
    return f"NailQue-Setup-{version}.exe"


def install_update(installer_path: str) -> None:
    escaped_path = installer_path.replace("'", "''")
    launch_candidate = str(Path(sys.executable)) if getattr(sys, "frozen", False) else ""
    launch_fallback = str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NailQue" / "NailQue.exe")
    launch_candidate_escaped = launch_candidate.replace("'", "''")
    launch_fallback_escaped = launch_fallback.replace("'", "''")
    script = (
        f"$installer = '{escaped_path}'; "
        "Start-Process -FilePath $installer -ArgumentList '/VERYSILENT','/NORESTART','/CLOSEAPPLICATIONS' -Verb RunAs -Wait; "
        f"$candidate = '{launch_candidate_escaped}'; "
        f"$fallback = '{launch_fallback_escaped}'; "
        "if ($candidate -and (Test-Path $candidate)) { Start-Process -FilePath $candidate } "
        "elseif (Test-Path $fallback) { Start-Process -FilePath $fallback }"
    )
    process = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        stderr = (process.stderr or "").strip() or "Update installation failed."
        raise RuntimeError(stderr)
