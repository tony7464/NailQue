import logging
import time
import uuid
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request, send_from_directory

from nailque.config import LOGS_DIR, WEB_DIR
from nailque.routes import register_blueprints

app = Flask(__name__, static_folder=None)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


def _setup_logging():
    app.logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(LOGS_DIR / "nailque.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
    package_logger = logging.getLogger("nailque")
    package_logger.setLevel(logging.INFO)
    if not package_logger.handlers:
        package_logger.addHandler(file_handler)


_setup_logging()
register_blueprints(app)


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
    return send_from_directory(WEB_DIR, "queue.html")


@app.errorhandler(500)
def handle_server_error(error):  # noqa: ARG001
    app.logger.exception("Unhandled server error at %s", request.path)
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error."}), 500
    return jsonify({"error": "Internal server error."}), 500
