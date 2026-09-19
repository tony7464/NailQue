"""HTML pages and public static assets."""

from __future__ import annotations

from flask import Blueprint, make_response, send_from_directory

from nailque.factory import get_ctx
from nailque.http import require_lan

pages_bp = Blueprint("pages", __name__)


def _html(filename: str):
    ctx = get_ctx()
    response = make_response(send_from_directory(ctx.paths.assets_dir, filename))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@pages_bp.route("/")
@pages_bp.route("/luxe-nails-queue.html")
def main_queue():
    return _html("luxe-nails-queue.html")


@pages_bp.route("/employee")
def employee_portal():
    return _html("luxe-nails-employee.html")


@pages_bp.route("/mobile")
@require_lan
def mobile_portal():
    return _html("luxe-nails-mobile.html")


@pages_bp.route("/assets/<path:filename>")
def public_assets(filename: str):
    ctx = get_ctx()
    return send_from_directory(ctx.paths.assets_public_dir, filename)
