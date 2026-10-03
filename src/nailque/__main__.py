import os
import sys
import threading
import webbrowser

from nailque.app import app
from nailque.config import APP_VERSION, RUNTIME_DIR, env_flag
from nailque.desktop import launch_desktop_window
from nailque.network import detect_lan_ip
from nailque.updater import launch_background_updater


def main() -> None:
    port = int(os.getenv("PORT", "5001"))
    host = os.getenv("HOST", "0.0.0.0")
    auto_open_browser = env_flag("AUTO_OPEN_BROWSER", True)
    use_desktop_window = env_flag("USE_DESKTOP_WINDOW", True)
    dev_reload = env_flag("DEV_RELOAD", False) and not getattr(sys, "frozen", False)
    print("\nNailQue started")
    print(f"   Queue           → http://localhost:{port}")
    print(f"   Employee Portal → http://localhost:{port}/employee")
    print(f"   Mobile Portal   → http://{detect_lan_ip()}:{port}/mobile")
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
        desktop_opened = launch_desktop_window(port)
        if not desktop_opened:
            if auto_open_browser:
                threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}/")).start()
            server_thread.join()
    else:
        if auto_open_browser:
            threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}/")).start()
        app.run(host=host, port=port, debug=dev_reload, use_reloader=dev_reload)


if __name__ == "__main__":
    main()
