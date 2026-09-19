"""Authenticated over-the-air update controls."""

from __future__ import annotations

import threading

from flask import Blueprint, jsonify

from nailque.factory import get_ctx
from nailque.http import require_manager

updates_bp = Blueprint("updates", __name__)


@updates_bp.route("/api/update/status", methods=["GET"])
@require_manager
def update_status():
    return jsonify(get_ctx().updater.snapshot())


@updates_bp.route("/api/update/check", methods=["POST"])
@require_manager
def trigger_update_check():
    ctx = get_ctx()
    if not ctx.updater.state["enabled"]:
        return jsonify({"ok": False, "error": "Auto-updater is disabled."}), 400
    threading.Thread(target=lambda: ctx.updater.check(download_if_available=True), daemon=True).start()
    return jsonify({"ok": True})


@updates_bp.route("/api/update/check-sync", methods=["POST"])
@require_manager
def trigger_update_check_sync():
    ctx = get_ctx()
    if not ctx.updater.state["enabled"]:
        return jsonify({"ok": False, "error": "Auto-updater is disabled."}), 400
    ctx.updater.check(download_if_available=True)
    return jsonify({"ok": True, "status": ctx.updater.snapshot()})


@updates_bp.route("/api/update/install", methods=["POST"])
@require_manager
def install_update():
    try:
        get_ctx().updater.install()
        return jsonify({"ok": True, "message": "Update installed. Relaunching NailQue..."})
    except RuntimeError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
