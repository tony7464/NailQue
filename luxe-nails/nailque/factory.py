"""Flask application factory and runtime context."""

from __future__ import annotations

import logging
import time
import uuid
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request

from nailque.managers import ManagerStore
from nailque.paths import AppPaths, load_environment
from nailque.queue import SharedStateStore
from nailque.records import JsonRecordStore
from nailque.security import RateLimiter
from nailque.sessions import TokenStore
from nailque.settings import Settings
from nailque.updates import Updater


class AppContext:
    def __init__(self, paths: AppPaths, settings: Settings, logger):
        self.paths = paths
        self.settings = settings
        self.logger = logger
        self.rate_limiter = RateLimiter()
        self.shared_state = SharedStateStore(paths.shared_state_file)
        self.managers = ManagerStore(
            paths.manager_settings_file,
            settings.manager_full_name,
            settings.manager_username,
            settings.manager_pin,
        )
        self.manager_sessions = TokenStore(settings.manager_session_ttl_seconds, bind_ip=True)
        self.mobile_sessions = TokenStore(settings.mobile_session_ttl_seconds, bind_ip=True)
        self.employee_sessions = TokenStore(settings.employee_session_ttl_seconds, bind_ip=True)
        self.activity = JsonRecordStore(paths.manager_activity_file, keep_last=300)
        self.service_history = JsonRecordStore(paths.service_history_file, keep_last=1000)
        self.updater = Updater(settings, paths.updates_dir, logger)
        self.removed_logins: dict[str, dict] = {}


def setup_logging(app: Flask, log_file) -> None:
    app.logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    if not any(isinstance(handler, RotatingFileHandler) for handler in app.logger.handlers):
        app.logger.addHandler(file_handler)


def create_app(paths: AppPaths | None = None) -> Flask:
    if paths is None:
        paths = AppPaths()
    load_environment(paths.assets_dir, paths.runtime_dir)
    settings = Settings(paths.assets_dir, paths.secret_key_file)

    app = Flask(
        __name__,
        static_folder=str(paths.static_dir),
        static_url_path="/static",
    )
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
    app.config["MAX_CONTENT_LENGTH"] = settings.max_content_length
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["NAILQUE_PATHS"] = paths
    app.config["NAILQUE_SETTINGS"] = settings

    setup_logging(app, paths.logs_dir / "nailque.log")
    context = AppContext(paths, settings, app.logger)
    app.extensions["nailque"] = context

    from nailque.routes.employee import employee_bp
    from nailque.routes.health import health_bp
    from nailque.routes.manager import manager_bp
    from nailque.routes.mobile import mobile_bp
    from nailque.routes.pages import pages_bp
    from nailque.routes.queue_api import queue_bp
    from nailque.routes.updates import updates_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(queue_bp)
    app.register_blueprint(mobile_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(updates_bp)

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
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-Id"] = request_id
        return response

    @app.errorhandler(404)
    def handle_not_found(error):  # noqa: ARG001
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(500)
    def handle_server_error(error):  # noqa: ARG001
        app.logger.exception("Unhandled server error at %s", request.path)
        return jsonify({"error": "Internal server error."}), 500

    return app


def get_ctx() -> AppContext:
    from flask import current_app, has_app_context

    if has_app_context():
        ctx = current_app.extensions.get("nailque")
        if ctx is not None:
            return ctx
    raise RuntimeError("NailQue application context is not available.")
