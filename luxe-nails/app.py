from flask import Flask, jsonify, request, send_from_directory
import base64
import json
import ipaddress
import io
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from urllib.error import URLError
from urllib.request import urlopen, Request
from dotenv import load_dotenv
import qrcode

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64KB request limit


def _get_paths():
    if getattr(sys, "frozen", False):
        assets_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        runtime_dir = Path.home() / "Library" / "Application Support" / "NailQue"
    else:
        assets_dir = Path(__file__).resolve().parent
        runtime_dir = assets_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return assets_dir, runtime_dir


ASSETS_DIR, RUNTIME_DIR = _get_paths()
load_dotenv(RUNTIME_DIR / ".env")
MANAGER_SETTINGS_FILE = RUNTIME_DIR / "manager_settings.json"
LOGS_DIR = RUNTIME_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
UPDATES_DIR = RUNTIME_DIR / "updates"
UPDATES_DIR.mkdir(parents=True, exist_ok=True)


def _load_app_version() -> str:
    version_file = ASSETS_DIR / "VERSION"
    if version_file.exists():
        try:
            version = version_file.read_text(encoding="utf-8").strip()
            if version:
                return version
        except OSError:
            pass
    return "1.0.0"


APP_VERSION = _load_app_version()
AUTO_UPDATE_REPO = os.getenv("AUTO_UPDATE_REPO", "").strip()
AUTO_UPDATE_ENABLED = os.getenv("AUTO_UPDATE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
AUTO_UPDATE_CHECK_INTERVAL_SECONDS = max(300, int(os.getenv("AUTO_UPDATE_CHECK_INTERVAL_SECONDS", "900")))
AUTO_UPDATE_INCLUDE_PRERELEASE = os.getenv("AUTO_UPDATE_INCLUDE_PRERELEASE", "false").strip().lower() in {"1", "true", "yes", "on"}
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
    "last_checked": 0,
    "last_error": "",
}
MOBILE_SESSIONS = {}
MOBILE_SESSION_TTL_SECONDS = 12 * 60 * 60
SHARED_STATE_LOCK = threading.Lock()
SHARED_STATE_FILE = RUNTIME_DIR / "shared_state.json"
SHARED_STATE = {}
SERVICE_HISTORY_FILE = RUNTIME_DIR / "service_history.json"
SERVICES_MENU = [
    {"name": "Spa Manicure", "price": 40},
    {"name": "Signature Manicure", "price": 50},
    {"name": "Ultimate M.V. Spa Manicure", "price": 65},
    {"name": "Spa Pedicure", "price": 60},
    {"name": "Signature Pedicure", "price": 70},
    {"name": "Full Set Acrylic", "price": 55},
    {"name": "Fill", "price": 40},
    {"name": "Gel Polish", "price": 25},
    {"name": "Polish Change", "price": 15},
    {"name": "Nail Art (per nail)", "price": 5},
    {"name": "Coffin / Stiletto Shape (+$5)", "price": 5},
    {"name": "Almond / Ballerina Shape (+$5)", "price": 5},
    {"name": "Paraffin Treatment", "price": 15},
    {"name": "Sugar Scrub", "price": 10},
    {"name": "Collagen Gloves", "price": 20},
    {"name": "Hot Stone Massage", "price": 15},
]


def _empty_shared_state():
    return {
        "techs": {},
        "waitingQueue": [],
        "nextCustomerId": 1,
        "bonusClockIns": {},
        "credentials": {},
        "updatedAt": int(time.time()),
    }


def _load_shared_state():
    global SHARED_STATE
    saved = _read_json(SHARED_STATE_FILE, _empty_shared_state())
    if not isinstance(saved, dict):
        saved = _empty_shared_state()
    for key, fallback in _empty_shared_state().items():
        if key not in saved:
            saved[key] = fallback
    SHARED_STATE = saved


def _persist_shared_state():
    with SHARED_STATE_LOCK:
        SHARED_STATE["updatedAt"] = int(time.time())
        _write_json_atomic(SHARED_STATE_FILE, SHARED_STATE)


def _detect_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _is_private_or_loopback(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def _is_same_lan_client(ip_text: str) -> bool:
    # Restrict to private/loopback ranges; this keeps access local-network only
    # while avoiding false negatives across different private subnet masks.
    return _is_private_or_loopback(ip_text)


def _request_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.remote_addr or ""


def _mobile_requires_lan():
    client_ip = _request_client_ip()
    if not _is_same_lan_client(client_ip):
        return jsonify({"error": "Mobile access is only allowed from the same local network."}), 403
    return None


def _qr_png_data_url(text: str) -> str:
    qr = qrcode.QRCode(border=2, box_size=6)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _safe_copy_shared_state():
    with SHARED_STATE_LOCK:
        return {
            "techs": dict(SHARED_STATE.get("techs") or {}),
            "waitingQueue": list(SHARED_STATE.get("waitingQueue") or []),
            "nextCustomerId": int(SHARED_STATE.get("nextCustomerId") or 1),
            "bonusClockIns": dict(SHARED_STATE.get("bonusClockIns") or {}),
            "credentials": dict(SHARED_STATE.get("credentials") or {}),
            "updatedAt": int(SHARED_STATE.get("updatedAt") or 0),
        }


def _cleanup_mobile_sessions():
    now = int(time.time())
    expired = [token for token, item in MOBILE_SESSIONS.items() if int(item.get("expiresAt") or 0) <= now]
    for token in expired:
        MOBILE_SESSIONS.pop(token, None)


def _get_active_mobile_techs():
    _cleanup_mobile_sessions()
    active = {}
    now = int(time.time())
    for session in MOBILE_SESSIONS.values():
        tech_name = str(session.get("tech") or "")
        if not tech_name:
            continue
        active[tech_name] = {
            "tech": tech_name,
            "ip": str(session.get("ip") or ""),
            "expiresInSeconds": max(0, int(session.get("expiresAt") or 0) - now),
        }
    return list(active.values())


def _resolve_mobile_session():
    _cleanup_mobile_sessions()
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.replace("Bearer ", "", 1).strip()
    session = MOBILE_SESSIONS.get(token)
    if not session:
        return None
    client_ip = _request_client_ip()
    if session.get("ip") != client_ip:
        return None
    return session


def _get_available_tech_order(state):
    techs = state.get("techs") or {}
    bonus_clock_ins = state.get("bonusClockIns") or {}
    return sorted(
        [name for name, details in techs.items() if details.get("status") == "Available"],
        key=lambda name: int(bonus_clock_ins.get(name) or (10**15)),
    )


def _try_auto_assign_shared_state(state):
    techs = state.get("techs") or {}
    queue = state.get("waitingQueue") or []
    bonus_clock_ins = state.get("bonusClockIns") or {}
    if not queue:
        return
    now_ms = int(time.time() * 1000)

    def assignable_index(tech_name):
        for idx, customer in enumerate(queue):
            appointment_time = customer.get("appointmentTime")
            requested = customer.get("requestedTech") or ""
            appointment_ready = not appointment_time or int(appointment_time) <= now_ms
            matches = (not requested) or (requested == tech_name)
            if appointment_ready and matches:
                return idx
        return -1

    while True:
        available_order = _get_available_tech_order(state)
        if not available_order or not queue:
            break
        assigned = False
        for tech_name in available_order:
            idx = assignable_index(tech_name)
            if idx < 0:
                continue
            customer = queue.pop(idx)
            tech = techs.get(tech_name) or {}
            tech["status"] = "Busy"
            tech["current"] = customer.get("name") or "Customer"
            tech["startTime"] = now_ms
            techs[tech_name] = tech
            assigned = True
            break
        if not assigned:
            break
    state["techs"] = techs
    state["waitingQueue"] = queue
    state["bonusClockIns"] = bonus_clock_ins


def _setup_logging():
    app.logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(LOGS_DIR / "nailque.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)


_setup_logging()


def _read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return fallback


def _write_json_atomic(path: Path, payload):
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    os.replace(temp_path, path)


_load_shared_state()


def _read_service_history():
    records = _read_json(SERVICE_HISTORY_FILE, [])
    if not isinstance(records, list):
        return []
    return records


def _append_service_history(record):
    records = _read_service_history()
    records.append(record)
    records = records[-1000:]
    _write_json_atomic(SERVICE_HISTORY_FILE, records)


def _build_service_details(selected_service_indexes):
    total = 0.0
    selected_indexes = []
    selected_services = []
    for idx in selected_service_indexes:
        if not isinstance(idx, int):
            continue
        if idx < 0 or idx >= len(SERVICES_MENU):
            continue
        selected_indexes.append(idx)
        svc = SERVICES_MENU[idx]
        selected_services.append(svc["name"])
        total += float(svc["price"])
    return {
        "selectedServiceIndexes": selected_indexes,
        "selectedServices": selected_services,
        "total": round(total, 2),
        "employeeShare": round(total * 0.6, 2),
    }


def _read_manager_settings():
    return _read_json(MANAGER_SETTINGS_FILE, {})


def _write_manager_settings(settings):
    _write_json_atomic(MANAGER_SETTINGS_FILE, settings)


def _get_manager_pin():
    settings = _read_manager_settings()
    if settings.get("pin"):
        return str(settings.get("pin"))
    default_pin = os.getenv("MANAGER_PIN", "1234")
    _write_manager_settings({"pin": default_pin})
    return str(default_pin)


def _set_manager_pin(new_pin):
    _write_manager_settings({"pin": str(new_pin)})


def _normalize_version(value: str):
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


def _is_newer_version(candidate: str, current: str) -> bool:
    return _normalize_version(candidate) > _normalize_version(current)


def _select_release_asset(release_payload):
    assets = release_payload.get("assets") or []
    preferred = None
    for asset in assets:
        name = str(asset.get("name") or "")
        if name.endswith(".pkg") and "NailQue-macOS" in name:
            preferred = asset
            break
    if preferred:
        return preferred
    for asset in assets:
        name = str(asset.get("name") or "")
        if name.endswith(".pkg"):
            return asset
    return None


def _fetch_latest_release(repo: str):
    if not repo:
        raise ValueError("AUTO_UPDATE_REPO is not configured.")
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    if AUTO_UPDATE_INCLUDE_PRERELEASE:
        api_url = f"https://api.github.com/repos/{repo}/releases?per_page=8"
    request_obj = Request(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "NailQue-Updater"})
    with urlopen(request_obj, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if AUTO_UPDATE_INCLUDE_PRERELEASE:
        if not isinstance(payload, list) or not payload:
            raise RuntimeError("No releases found.")
        release = payload[0]
    else:
        release = payload
    tag_name = str(release.get("tag_name") or "").strip()
    if not tag_name:
        raise RuntimeError("Latest release is missing tag_name.")
    version = tag_name[1:] if tag_name.lower().startswith("v") else tag_name
    asset = _select_release_asset(release)
    if not asset:
        raise RuntimeError("No .pkg asset found on latest release.")
    return {
        "version": version,
        "release_name": str(release.get("name") or tag_name),
        "release_notes": str(release.get("body") or ""),
        "asset_name": str(asset.get("name") or ""),
        "asset_url": str(asset.get("browser_download_url") or ""),
    }


def _download_update_asset(asset_name: str, asset_url: str, version: str) -> str:
    if not asset_url:
        raise RuntimeError("Update asset URL is missing.")
    safe_name = f"NailQue-macOS-{version}.pkg"
    if asset_name.endswith(".pkg"):
        safe_name = asset_name
    target = UPDATES_DIR / safe_name
    temp_target = target.with_suffix(target.suffix + ".partial")
    request_obj = Request(asset_url, headers={"User-Agent": "NailQue-Updater"})
    with urlopen(request_obj, timeout=40) as response, temp_target.open("wb") as file:
        shutil.copyfileobj(response, file)
    os.replace(temp_target, target)
    return str(target)


def _set_update_error(message: str):
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
        release = _fetch_latest_release(UPDATE_STATE["repo"])
        with UPDATE_LOCK:
            UPDATE_STATE["latest_version"] = release["version"]
            UPDATE_STATE["release_name"] = release["release_name"]
            UPDATE_STATE["release_notes"] = release["release_notes"]
            UPDATE_STATE["asset_name"] = release["asset_name"]
            UPDATE_STATE["asset_url"] = release["asset_url"]
            UPDATE_STATE["available"] = _is_newer_version(release["version"], APP_VERSION)
            UPDATE_STATE["last_checked"] = int(time.time())
        if download_if_available and UPDATE_STATE["available"]:
            downloaded_path = _download_update_asset(release["asset_name"], release["asset_url"], release["version"])
            with UPDATE_LOCK:
                UPDATE_STATE["downloaded_path"] = downloaded_path
    except (ValueError, RuntimeError, OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
        _set_update_error(str(error))
        return
    with UPDATE_LOCK:
        UPDATE_STATE["checking"] = False


def background_update_loop():
    while True:
        check_for_updates(download_if_available=True)
        time.sleep(AUTO_UPDATE_CHECK_INTERVAL_SECONDS)


def launch_background_updater():
    if not UPDATE_STATE["enabled"]:
        app.logger.info("Auto-updater disabled. Set AUTO_UPDATE_REPO to enable OTA updates.")
        return
    thread = threading.Thread(target=background_update_loop, daemon=True)
    thread.start()
    app.logger.info("Background auto-updater enabled for repo %s", UPDATE_STATE["repo"])


def get_update_status():
    with UPDATE_LOCK:
        return dict(UPDATE_STATE)


def install_downloaded_update():
    status = get_update_status()
    pkg_path = status.get("downloaded_path") or ""
    if not pkg_path or not Path(pkg_path).exists():
        raise RuntimeError("No downloaded update package available.")
    escaped_path = pkg_path.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'do shell script '
        f'"installer -pkg \\"{escaped_path}\\" -target / && open \\"/Applications/NailQue.app\\"" '
        "with administrator privileges"
    )
    process = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if process.returncode != 0:
        stderr = (process.stderr or "").strip() or "Update installation failed."
        raise RuntimeError(stderr)

def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@app.before_request
def before_request_logging():
    request._start_time = time.time()  # noqa: SLF001
    request._request_id = uuid.uuid4().hex[:10]  # noqa: SLF001


@app.after_request
def add_security_headers(response):
    duration_ms = int((time.time() - getattr(request, "_start_time", time.time())) * 1000)
    request_id = getattr(request, "_request_id", "unknown")
    app.logger.info("%s %s %s %sms id=%s", request.method, request.path, response.status_code, duration_ms, request_id)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-Id"] = request_id
    return response


@app.errorhandler(404)
def handle_not_found(error):  # noqa: ARG001
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(ASSETS_DIR, "luxe-nails-queue.html")


@app.errorhandler(500)
def handle_server_error(error):  # noqa: ARG001
    app.logger.exception("Unhandled server error at %s", request.path)
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error."}), 500
    return jsonify({"error": "Internal server error."}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "nailque",
        "version": APP_VERSION,
        "runtime_dir": str(RUNTIME_DIR),
    })


@app.route("/api/manager/verify-pin", methods=["POST"])
def verify_manager_pin():
    entered = str((request.get_json(silent=True) or {}).get("pin") or "")
    manager_pin = _get_manager_pin()
    return jsonify({"ok": entered == manager_pin})


@app.route("/api/manager/set-pin", methods=["POST"])
def set_manager_pin():
    payload = request.get_json(silent=True) or {}
    current_pin = str(payload.get("currentPin") or "")
    new_pin = str(payload.get("newPin") or "")

    if current_pin != _get_manager_pin():
        return jsonify({"error": "Current PIN is incorrect."}), 400
    if not new_pin.isdigit() or len(new_pin) < 4:
        return jsonify({"error": "New PIN must be at least 4 digits."}), 400

    _set_manager_pin(new_pin)
    app.logger.info("Manager PIN updated")
    return jsonify({"ok": True})


@app.route("/api/update/status", methods=["GET"])
def update_status():
    return jsonify(get_update_status())


@app.route("/api/update/check", methods=["POST"])
def trigger_update_check():
    threading.Thread(target=lambda: check_for_updates(download_if_available=True), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/update/check-sync", methods=["POST"])
def trigger_update_check_sync():
    check_for_updates(download_if_available=True)
    return jsonify({"ok": True, "status": get_update_status()})


@app.route("/api/update/install", methods=["POST"])
def install_update():
    try:
        install_downloaded_update()
        return jsonify({"ok": True, "message": "Update installed. Relaunching NailQue..."})
    except RuntimeError as error:
        return jsonify({"ok": False, "error": str(error)}), 400


@app.route("/api/network-info", methods=["GET"])
def network_info():
    lan_ip = _detect_lan_ip()
    port = int(os.getenv("PORT", "5001"))
    mobile_url = f"http://{lan_ip}:{port}/mobile"
    return jsonify({
        "ok": True,
        "lan_ip": lan_ip,
        "mobile_url": mobile_url,
        "mobile_qr_data_url": _qr_png_data_url(mobile_url),
    })


@app.route("/api/shared/sync", methods=["POST"])
def shared_sync():
    payload = request.get_json(silent=True) or {}
    with SHARED_STATE_LOCK:
        if isinstance(payload.get("techs"), dict):
            SHARED_STATE["techs"] = payload.get("techs")
        if isinstance(payload.get("waitingQueue"), list):
            SHARED_STATE["waitingQueue"] = payload.get("waitingQueue")
        if isinstance(payload.get("bonusClockIns"), dict):
            SHARED_STATE["bonusClockIns"] = payload.get("bonusClockIns")
        if isinstance(payload.get("credentials"), dict):
            SHARED_STATE["credentials"] = payload.get("credentials")
        if isinstance(payload.get("nextCustomerId"), int):
            SHARED_STATE["nextCustomerId"] = payload.get("nextCustomerId")
        _try_auto_assign_shared_state(SHARED_STATE)
    _persist_shared_state()
    return jsonify({"ok": True, "state": _safe_copy_shared_state()})


@app.route("/api/shared/state", methods=["GET"])
def shared_state():
    return jsonify({"ok": True, "state": _safe_copy_shared_state()})


@app.route("/api/services/history", methods=["GET"])
def services_history():
    records = _read_service_history()
    return jsonify({"ok": True, "records": records[-200:]})


@app.route("/api/services/record", methods=["POST"])
def services_record():
    payload = request.get_json(silent=True) or {}
    tech_name = str(payload.get("tech") or "").strip()
    customer_name = str(payload.get("customer") or "Customer").strip() or "Customer"
    selected_indexes = payload.get("selectedServiceIndexes") or []
    if not isinstance(selected_indexes, list):
        selected_indexes = []
    selected_indexes = [int(i) for i in selected_indexes if isinstance(i, int)]
    details = _build_service_details(selected_indexes)
    completed_at = str(payload.get("completedAt") or "") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    source = str(payload.get("source") or "frontdesk")
    record = {
        "tech": tech_name,
        "customer": customer_name,
        "selectedServiceIndexes": details["selectedServiceIndexes"],
        "selectedServices": details["selectedServices"],
        "total": details["total"],
        "employeeShare": details["employeeShare"],
        "completedAt": completed_at,
        "source": source,
    }
    _append_service_history(record)
    return jsonify({"ok": True, "record": record})


@app.route("/api/mobile/login", methods=["POST"])
def mobile_login():
    blocked = _mobile_requires_lan()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    identifier = str(payload.get("identifier") or "").strip().lower()
    password = str(payload.get("password") or "")
    with SHARED_STATE_LOCK:
        credentials = dict(SHARED_STATE.get("credentials") or {})
    matched_tech = None
    for tech_name, cred in credentials.items():
        saved_identifier = str((cred or {}).get("identifier") or "").strip().lower()
        saved_password = str((cred or {}).get("password") or "")
        if identifier == saved_identifier and password == saved_password:
            matched_tech = tech_name
            break
    if not matched_tech:
        return jsonify({"ok": False, "error": "Invalid login credentials."}), 401
    token = uuid.uuid4().hex
    MOBILE_SESSIONS[token] = {
        "tech": matched_tech,
        "ip": _request_client_ip(),
        "expiresAt": int(time.time()) + MOBILE_SESSION_TTL_SECONDS,
    }
    return jsonify({"ok": True, "token": token, "tech": matched_tech})


@app.route("/api/mobile/state", methods=["GET"])
def mobile_state():
    blocked = _mobile_requires_lan()
    if blocked:
        return blocked
    session = _resolve_mobile_session()
    if not session:
        return jsonify({"ok": False, "error": "Unauthorized."}), 401
    state = _safe_copy_shared_state()
    techs = state.get("techs") or {}
    techs_overview = [
        {
            "name": name,
            "status": str((details or {}).get("status") or "Offline"),
            "current": str((details or {}).get("current") or ""),
            "startTime": (details or {}).get("startTime"),
        }
        for name, details in techs.items()
    ]
    techs_overview.sort(key=lambda item: item["name"].lower())
    return jsonify({
        "ok": True,
        "tech": session.get("tech"),
        "techState": techs.get(session.get("tech")) or {},
        "waitingQueue": state.get("waitingQueue") or [],
        "techsOverview": techs_overview,
        "servicesMenu": SERVICES_MENU,
        "serviceHistory": _read_service_history()[-80:],
    })


@app.route("/api/mobile/action", methods=["POST"])
def mobile_action():
    blocked = _mobile_requires_lan()
    if blocked:
        return blocked
    session = _resolve_mobile_session()
    if not session:
        return jsonify({"ok": False, "error": "Unauthorized."}), 401
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    tech_name = session.get("tech")
    with SHARED_STATE_LOCK:
        techs = SHARED_STATE.get("techs") or {}
        tech = techs.get(tech_name)
        if not tech:
            return jsonify({"ok": False, "error": "Tech not found."}), 404
        now_ms = int(time.time() * 1000)
        if action == "clock_in":
            if tech.get("status") not in {"Busy", "Scheduled Appointment"}:
                tech["status"] = "Available"
                bonus_clock_ins = SHARED_STATE.get("bonusClockIns") or {}
                if not bonus_clock_ins.get(tech_name):
                    bonus_clock_ins[tech_name] = now_ms
                SHARED_STATE["bonusClockIns"] = bonus_clock_ins
        elif action == "break":
            if tech.get("status") == "Busy":
                return jsonify({"ok": False, "error": "Cannot start break while busy."}), 400
            tech["status"] = "On Break"
            tech["current"] = None
            tech["startTime"] = None
        elif action == "end_break":
            if tech.get("status") == "On Break":
                tech["status"] = "Available"
                bonus_clock_ins = SHARED_STATE.get("bonusClockIns") or {}
                if not bonus_clock_ins.get(tech_name):
                    bonus_clock_ins[tech_name] = now_ms
                SHARED_STATE["bonusClockIns"] = bonus_clock_ins
        elif action == "finish_customer":
            selected_indexes_raw = payload.get("selectedServiceIndexes") or []
            if not isinstance(selected_indexes_raw, list):
                return jsonify({"ok": False, "error": "Service selection is invalid."}), 400
            selected_indexes = [int(i) for i in selected_indexes_raw if isinstance(i, int)]
            details = _build_service_details(selected_indexes)
            completed_customer_name = str(tech.get("current") or "Customer")
            completion_record = {
                "tech": tech_name,
                "customer": completed_customer_name,
                "selectedServiceIndexes": details["selectedServiceIndexes"],
                "selectedServices": details["selectedServices"],
                "total": details["total"],
                "employeeShare": details["employeeShare"],
                "completedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "mobile",
            }
            tech["earnings"] = round(float(tech.get("earnings") or 0) + details["employeeShare"], 2)
            tech["status"] = "Available"
            tech["current"] = None
            tech["startTime"] = None
            bonus_clock_ins = SHARED_STATE.get("bonusClockIns") or {}
            if not bonus_clock_ins.get(tech_name):
                bonus_clock_ins[tech_name] = now_ms
            SHARED_STATE["bonusClockIns"] = bonus_clock_ins
            _append_service_history(completion_record)
        elif action == "unready":
            if tech.get("status") == "Busy":
                return jsonify({"ok": False, "error": "Cannot go unready while busy."}), 400
            tech["status"] = "Offline"
            tech["current"] = None
            tech["startTime"] = None
        else:
            return jsonify({"ok": False, "error": "Unsupported action."}), 400
        techs[tech_name] = tech
        SHARED_STATE["techs"] = techs
        _try_auto_assign_shared_state(SHARED_STATE)
    _persist_shared_state()
    return jsonify({"ok": True, "state": _safe_copy_shared_state()})


@app.route("/api/mobile/active-techs", methods=["GET"])
def mobile_active_techs():
    blocked = _mobile_requires_lan()
    if blocked:
        return blocked
    return jsonify({"ok": True, "activeTechs": _get_active_mobile_techs()})


@app.route("/")
def main_queue():
    return send_from_directory(ASSETS_DIR, "luxe-nails-queue.html")


@app.route("/employee")
def employee_portal():
    return send_from_directory(ASSETS_DIR, "luxe-nails-employee.html")


@app.route("/mobile")
def mobile_portal():
    blocked = _mobile_requires_lan()
    if blocked:
        return blocked
    return send_from_directory(ASSETS_DIR, "luxe-nails-mobile.html")


@app.route("/<path:path>")
def serve_file(path):
    return send_from_directory(ASSETS_DIR, path)


def _wait_for_server(port: int, timeout_seconds: float = 12.0) -> bool:
    deadline = time.time() + timeout_seconds
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _launch_desktop_window(port: int) -> bool:
    try:
        import webview  # pywebview
    except Exception:
        app.logger.exception("pywebview is unavailable; falling back to browser mode")
        return False

    if not _wait_for_server(port):
        app.logger.error("Server did not become ready for desktop window mode")
        return False

    webview.create_window(
        "NailQue",
        f"http://127.0.0.1:{port}/",
        width=1480,
        height=940,
        min_size=(1100, 720),
    )
    webview.start()
    return True


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    host = os.getenv("HOST", "0.0.0.0")
    auto_open_browser = _env_flag("AUTO_OPEN_BROWSER", True)
    use_desktop_window = _env_flag("USE_DESKTOP_WINDOW", True)
    dev_reload = _env_flag("DEV_RELOAD", False) and not getattr(sys, "frozen", False)
    print("\n🚀 NailQue started")
    print(f"   Queue           → http://localhost:{port}")
    print(f"   Employee Portal → http://localhost:{port}/employee")
    print(f"   Mobile Portal   → http://{_detect_lan_ip()}:{port}/mobile")
    print(f"   Health          → http://localhost:{port}/api/health")
    print(f"   Runtime dir     → {RUNTIME_DIR}")
    print(f"   App version     → {APP_VERSION}")
    if dev_reload:
        print("   Dev reload      → enabled")
    print("   Press Ctrl+C to stop\n")
    is_reloader_primary = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if not dev_reload or is_reloader_primary:
        launch_background_updater()
    if getattr(sys, "frozen", False) and use_desktop_window:
        server_thread = threading.Thread(
            target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
            daemon=True,
        )
        server_thread.start()
        desktop_opened = _launch_desktop_window(port)
        if not desktop_opened:
            if auto_open_browser:
                threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}/")).start()
            server_thread.join()
    else:
        if auto_open_browser:
            threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}/")).start()
        app.run(host=host, port=port, debug=dev_reload, use_reloader=dev_reload)
