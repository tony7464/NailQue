import logging
import time
from urllib.request import urlopen

LOGGER = logging.getLogger("nailque")


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


def launch_desktop_window(port: int) -> bool:
    try:
        import webview
    except Exception:
        LOGGER.exception("pywebview is unavailable; falling back to browser mode")
        return False

    if not wait_for_server(port):
        LOGGER.error("Server did not become ready for desktop window mode")
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
