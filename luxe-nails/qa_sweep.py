import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _http_get(url: str, timeout: float = 4.0):
    req = Request(url, method="GET")
    with urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="ignore")
        return response.status, body


def _http_post_json(url: str, payload: dict, timeout: float = 4.0, headers: dict | None = None):
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="ignore")
        return response.status, body


def _wait_for_port(host: str, port: int, timeout_s: float = 12.0):
    start = time.time()
    while time.time() - start < timeout_s:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.75)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _record(results: list, name: str, ok: bool, details: str):
    results.append({"name": name, "ok": ok, "details": details})


def run_qa() -> int:
    root = Path(__file__).resolve().parent
    port = int(os.getenv("PORT", "5001"))
    host = "127.0.0.1"
    base = f"http://{host}:{port}"
    results = []

    required_files = [
        "app.py",
        "luxe-nails-queue.html",
        "luxe-nails-employee.html",
        "luxe-nails-mobile.html",
        "static/js/http.js",
        "static/js/queue.js",
        "static/css/queue.css",
        "nailque/factory.py",
        "requirements.txt",
        ".env.example",
        "build_executable.py",
        "package-release.py",
    ]
    for file_name in required_files:
        exists = (root / file_name).exists()
        _record(
            results,
            f"File exists: {file_name}",
            exists,
            "Found" if exists else "Missing required file",
        )

    env = os.environ.copy()
    env.setdefault("PORT", str(port))
    env["AUTO_OPEN_BROWSER"] = "false"
    env["AUTO_UPDATE_ENABLED"] = "false"
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )

    try:
        started = _wait_for_port(host, port, timeout_s=15.0)
        _record(results, "Server starts", started, f"Port {port} opened" if started else "Server did not start in time")
        if started:
            for route in ["/", "/employee", "/api/health"]:
                try:
                    status, body = _http_get(base + route)
                    ok = status == 200
                    _record(results, f"GET {route}", ok, f"status={status}")
                    if route == "/api/health" and ok:
                        try:
                            payload = json.loads(body)
                            _record(
                                results,
                                "Health payload shape",
                                bool(payload.get("ok") and payload.get("service") == "nailque" and "runtime_dir" not in payload),
                                "health JSON validated",
                            )
                        except json.JSONDecodeError:
                            _record(results, "Health payload shape", False, "health endpoint returned non-JSON")
                except URLError as err:
                    _record(results, f"GET {route}", False, f"request failed: {err}")

            try:
                status, body = _http_post_json(base + "/api/manager/verify-pin", {"username": "admin", "pin": "1234"})
                payload = json.loads(body)
                ok = status == 200 and payload.get("ok") is True and bool(payload.get("token"))
                _record(results, "POST /api/manager/verify-pin", ok, f"status={status}")
                token = payload.get("token") if ok else ""
            except (URLError, json.JSONDecodeError) as err:
                token = ""
                _record(results, "POST /api/manager/verify-pin", False, f"request failed: {err}")

            try:
                status, body = _http_get(base + "/api/shared/state")
                payload = json.loads(body)
                dumped = json.dumps(payload)
                ok = status == 200 and payload.get("ok") is True and "password" not in dumped
                _record(results, "Shared state hides passwords", ok, f"status={status}")
            except (URLError, json.JSONDecodeError) as err:
                _record(results, "Shared state hides passwords", False, f"request failed: {err}")

            try:
                status, _body = _http_post_json(base + "/api/manager/create-account", {"fullName": "Pat Lee", "username": "qa", "pin": "2222"})
                _record(results, "Unauthenticated manager create is blocked", status == 401, f"status={status}")
            except HTTPError as err:
                _record(results, "Unauthenticated manager create is blocked", err.code == 401, f"status={err.code}")
            except URLError as err:
                _record(results, "Unauthenticated manager create is blocked", False, f"request failed: {err}")

            if token:
                try:
                    req = Request(base + "/api/manager/accounts", method="GET")
                    req.add_header("Authorization", f"Bearer {token}")
                    with urlopen(req, timeout=4) as response:
                        status = response.status
                        body = response.read().decode("utf-8", errors="ignore")
                    payload = json.loads(body)
                    _record(results, "Authenticated manager accounts", status == 200 and payload.get("ok") is True, f"status={status}")
                except (URLError, json.JSONDecodeError) as err:
                    _record(results, "Authenticated manager accounts", False, f"request failed: {err}")

            try:
                status, _body = _http_get(base + "/luxe-nails-queue.html")
                _record(results, "GET /luxe-nails-queue.html", status == 200, f"status={status}")
            except URLError as err:
                _record(results, "GET /luxe-nails-queue.html", False, f"request failed: {err}")

            try:
                status, body = _http_get(base + "/app.py")
                _record(results, "Source file is not served", status == 404 and "from flask import" not in body, f"status={status}")
            except HTTPError as err:
                _record(results, "Source file is not served", err.code == 404, f"status={err.code}")
            except URLError as err:
                _record(results, "Source file is not served", False, f"request failed: {err}")

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=4)
        except Exception:
            proc.kill()

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    failed = total - passed

    report = {
        "generatedAt": datetime.now().isoformat(),
        "summary": {"total": total, "passed": passed, "failed": failed},
        "results": results,
    }

    reports_dir = root / "qa-reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / f"qa-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"QA report written: {report_file}")
    print(f"Passed: {passed}/{total}")
    if failed:
        print("Failures:")
        for item in results:
            if not item["ok"]:
                print(f"- {item['name']}: {item['details']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_qa())
