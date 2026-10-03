from flask import Blueprint, make_response, send_from_directory

from nailque.config import ASSETS_DIR, WEB_DIR
from nailque.network import mobile_requires_lan

bp = Blueprint("pages", __name__)


def _html_response(filename: str):
    response = make_response(send_from_directory(WEB_DIR, filename))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.route("/")
def main_queue():
    return _html_response("queue.html")


@bp.route("/employee")
def employee_portal():
    return _html_response("employee.html")


@bp.route("/mobile")
def mobile_portal():
    blocked = mobile_requires_lan()
    if blocked:
        return blocked
    return _html_response("mobile.html")


@bp.route("/web/<path:path>")
def serve_web(path):
    return send_from_directory(WEB_DIR, path)


@bp.route("/assets/<path:path>")
def serve_assets(path):
    return send_from_directory(ASSETS_DIR / "assets", path)
