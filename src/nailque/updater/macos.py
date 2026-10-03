import subprocess


PREFERRED_EXTENSIONS = [".pkg"]
PREFERRED_NAME_HINTS = ["NailQue-macOS"]


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
    return ".pkg"


def safe_download_name(asset_name: str, version: str) -> str:
    if asset_name.endswith(".pkg"):
        return asset_name
    return f"NailQue-macOS-{version}.pkg"


def install_update(installer_path: str) -> None:
    escaped_path = installer_path.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'do shell script '
        f'"installer -pkg \\"{escaped_path}\\" -target / && '
        f'(pkill -x NailQue || true) && '
        f'(pkill -f \\"/Applications/NailQue.app/Contents/MacOS/NailQue\\" || true) && '
        f'sleep 1 && open -n \\"/Applications/NailQue.app\\"" '
        "with administrator privileges"
    )
    process = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if process.returncode != 0:
        stderr = (process.stderr or "").strip() or "Update installation failed."
        raise RuntimeError(stderr)
