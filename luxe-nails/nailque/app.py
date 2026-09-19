"""Process entry point for source runs and packaged executables."""

from __future__ import annotations

import os
import threading
import time
import webbrowser
from urllib.request import urlopen

from nailque.factory import create_app
from nailque.network import detect_lan_ip


def wait_for_server(port: int, timeout_seconds: float = 12.0) -> bool:
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


def launch_desktop_window(app, port: int) -> bool:
    try:
        import webview
    except Exception:
        app.logger.exception("pywebview is unavailable; falling back to browser mode")
        return False
    if not wait_for_server(port):
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


def main() -> None:
    app = create_app()
    ctx = app.extensions["nailque"]
    settings = ctx.settings
    print("\nNailQue started")
    print(f"   Queue           -> http://localhost:{settings.port}")
    print(f"   Employee Portal -> http://localhost:{settings.port}/employee")
    print(f"   Mobile Portal   -> http://{detect_lan_ip()}:{settings.port}/mobile")
    print(f"   Health          -> http://localhost:{settings.port}/api/health")
    print(f"   App version     -> {settings.app_version}")
    if settings.dev_reload:
        print("   Dev reload      -> enabled")
    print("   Press Ctrl+C to stop\n")

    is_reloader_primary = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if not settings.dev_reload or is_reloader_primary:
        ctx.updater.start_background_loop()

    if settings.is_frozen and settings.use_desktop_window:
        server_thread = threading.Thread(
            target=lambda: app.run(host=settings.host, port=settings.port, debug=False, use_reloader=False),
            daemon=True,
        )
        server_thread.start()
        desktop_opened = launch_desktop_window(app, settings.port)
        if not desktop_opened:
            if settings.auto_open_browser:
                threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{settings.port}/")).start()
            server_thread.join()
        return

    if settings.auto_open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{settings.port}/")).start()
    app.run(host=settings.host, port=settings.port, debug=settings.dev_reload, use_reloader=settings.dev_reload)
