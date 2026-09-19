"""Employee portal login and weekly totals."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from nailque.factory import get_ctx
from nailque.http import client_ip, rate_limited, require_employee, require_lan

employee_bp = Blueprint("employee", __name__)


@employee_bp.route("/api/employee/login", methods=["POST"])
@require_lan
@rate_limited("employee-login", limit=8, window_seconds=300)
def employee_login():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    identifier = str(payload.get("identifier") or "").strip().lower()
    password = str(payload.get("password") or "")
    tech_name, cred = ctx.shared_state.authenticate_tech(identifier, password)
    if not tech_name or cred is None:
        return jsonify({"ok": False, "error": "Invalid credentials."}), 401
    token = ctx.employee_sessions.create({"tech": tech_name, "identifier": identifier}, client_ip())
    return jsonify({
        "ok": True,
        "token": token,
        "tech": tech_name,
        "mustChangePassword": bool(cred.get("mustChangePassword")),
    })


@employee_bp.route("/api/employee/history", methods=["GET"])
@require_lan
@require_employee
def employee_history():
    ctx = get_ctx()
    tech_name = request.employee_session.get("tech")
    records = [record for record in ctx.service_history.read() if record.get("tech") == tech_name]
    return jsonify({"ok": True, "tech": tech_name, "records": records[-200:]})


@employee_bp.route("/api/tech/change-password", methods=["POST"])
@require_lan
@rate_limited("employee-password", limit=8, window_seconds=300)
def employee_change_password():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    identifier = str(payload.get("identifier") or "").strip().lower()
    current_password = str(payload.get("currentPassword") or "")
    new_password = str(payload.get("newPassword") or "").strip()
    if not identifier or not current_password or not new_password:
        return jsonify({"ok": False, "error": "Identifier, current password, and new password are required."}), 400
    if len(new_password) < 4 or len(new_password) > 128:
        return jsonify({"ok": False, "error": "New password must be 4 to 128 characters."}), 400
    if new_password == current_password:
        return jsonify({"ok": False, "error": "New password must be different from current password."}), 400
    try:
        tech_name = ctx.shared_state.update_tech_password_by_identifier(identifier, current_password, new_password)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 401
    return jsonify({"ok": True, "tech": tech_name})
