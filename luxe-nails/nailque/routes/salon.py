"""First-run setup, salon settings, and end-of-day close."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from nailque.factory import get_ctx
from nailque.http import client_ip, rate_limited, require_lan, require_manager

salon_bp = Blueprint("salon", __name__)


@salon_bp.route("/api/setup/status", methods=["GET"])
def setup_status():
    ctx = get_ctx()
    return jsonify({
        "ok": True,
        "setupComplete": ctx.managers.is_setup_complete(),
        "salonName": ctx.salon.salon_name(),
        "tagline": ctx.salon.public().get("tagline") or "NAIL SPA",
    })


@salon_bp.route("/api/setup", methods=["POST"])
@rate_limited("setup", limit=6, window_seconds=600)
def complete_setup():
    ctx = get_ctx()
    if ctx.managers.is_setup_complete():
        return jsonify({"ok": False, "error": "Salon setup is already complete."}), 409
    payload = request.get_json(silent=True) or {}
    salon_name = str(payload.get("salonName") or "").strip()
    tagline = str(payload.get("tagline") or "NAIL SPA").strip() or "NAIL SPA"
    full_name = str(payload.get("fullName") or "").strip()
    username = str(payload.get("username") or "").strip().lower()
    pin = str(payload.get("pin") or "").strip()
    if not salon_name:
        return jsonify({"ok": False, "error": "Salon name is required."}), 400
    try:
        manager = ctx.managers.complete_setup(full_name, username, pin)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    ctx.salon.mark_setup_complete(salon_name, tagline)
    token = ctx.manager_sessions.create(
        {"username": manager["username"], "fullName": manager["fullName"]},
        client_ip(),
    )
    ctx.logger.info("First-run setup completed for manager %s", manager["username"])
    return jsonify({
        "ok": True,
        "token": token,
        "manager": manager,
        "salon": ctx.salon.public(),
        "mustChangePin": bool(manager.get("mustChangePin")),
    })


@salon_bp.route("/api/salon/settings", methods=["GET"])
@require_lan
def get_salon_settings():
    ctx = get_ctx()
    return jsonify({
        "ok": True,
        "settings": ctx.salon.public(),
        "setupComplete": ctx.managers.is_setup_complete(),
    })


@salon_bp.route("/api/salon/settings", methods=["PUT"])
@require_manager
def update_salon_settings():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    settings = ctx.salon.update(payload)
    return jsonify({"ok": True, "settings": settings})


@salon_bp.route("/api/salon/end-of-day", methods=["POST"])
@require_manager
def end_of_day():
    ctx = get_ctx()
    snapshot = ctx.shared_state.end_of_day()
    completed_today = []
    day_key = snapshot["closedAt"][:10]
    day_total = 0.0
    for record in ctx.service_history.read():
        completed = str(record.get("completedAt") or "")
        if completed.startswith(day_key):
            completed_today.append(record)
            day_total += float(record.get("total") or 0)
    closing = {
        "closedAt": snapshot["closedAt"],
        "salonName": ctx.salon.salon_name(),
        "waitingAtClose": snapshot["waitingQueue"],
        "appointmentsAtClose": snapshot["appointments"],
        "techsAtClose": snapshot["techs"],
        "completedCount": len(completed_today),
        "completedTotal": round(day_total, 2),
        "actor": str((getattr(request, "manager_session", {}) or {}).get("fullName") or "Manager"),
    }
    ctx.daily_closings.append(closing)
    ctx.activity.append({
        "message": f"Ended salon day. {len(snapshot['waitingQueue'])} waiting guests archived.",
        "actor": closing["actor"],
        "level": "success",
        "timestamp": snapshot["closedAt"],
    })
    return jsonify({
        "ok": True,
        "closing": closing,
        "state": ctx.shared_state.copy_for_client(),
    })


@salon_bp.route("/api/salon/closings", methods=["GET"])
@require_manager
def list_closings():
    ctx = get_ctx()
    return jsonify({"ok": True, "records": ctx.daily_closings.read()[-60:]})
