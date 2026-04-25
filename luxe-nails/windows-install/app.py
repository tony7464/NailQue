from flask import Flask, jsonify, request, send_from_directory
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
import time
import uuid
import webbrowser
from urllib.request import urlopen
from dotenv import load_dotenv

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64KB request limit


def _get_paths():
    if getattr(sys, "frozen", False):
        assets_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        if os.name == "nt":
            app_data = os.getenv("APPDATA")
            runtime_dir = Path(app_data) / "NailQue" if app_data else Path.home() / "AppData" / "Roaming" / "NailQue"
        else:
            runtime_dir = Path.home() / ".nailque"
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
        "version": "1.0.0",
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


@app.route("/")
def main_queue():
    return send_from_directory(ASSETS_DIR, "luxe-nails-queue.html")


@app.route("/employee")
def employee_portal():
    return send_from_directory(ASSETS_DIR, "luxe-nails-employee.html")


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
    host = "127.0.0.1"
    auto_open_browser = os.getenv("AUTO_OPEN_BROWSER", "true").lower() == "true"
    use_desktop_window = os.getenv("USE_DESKTOP_WINDOW", "true").lower() == "true"
    print("\n🚀 NailQue started")
    print(f"   Queue           → http://localhost:{port}")
    print(f"   Employee Portal → http://localhost:{port}/employee")
    print(f"   Health          → http://localhost:{port}/api/health")
    print(f"   Runtime dir     → {RUNTIME_DIR}")
    print("   Press Ctrl+C to stop\n")
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
        app.run(host=host, port=port, debug=False, use_reloader=False)
