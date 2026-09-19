"""Authenticated manager APIs: accounts, activity, and tech logins."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from nailque.factory import get_ctx
from nailque.http import client_ip, rate_limited, require_manager
from nailque.managers import public_manager
from nailque.records import sanitize_activity_entry

manager_bp = Blueprint("manager", __name__)


@manager_bp.route("/api/manager/verify-pin", methods=["POST"])
@rate_limited("manager-pin", limit=8, window_seconds=300)
def verify_manager_pin():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip().lower()
    pin = str(payload.get("pin") or "")
    manager = ctx.managers.authenticate(username, pin)
    if not manager:
        return jsonify({"ok": False})
    token = ctx.manager_sessions.create(
        {"username": manager["username"], "fullName": manager["fullName"]},
        client_ip(),
    )
    return jsonify({"ok": True, "token": token, "manager": public_manager(manager)})


@manager_bp.route("/api/manager/set-pin", methods=["POST"])
@require_manager
def set_manager_pin():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    session = request.manager_session
    current_pin = str(payload.get("currentPin") or "")
    new_pin = str(payload.get("newPin") or "")
    if not new_pin.isdigit() or not (4 <= len(new_pin) <= 12):
        return jsonify({"error": "New PIN must be 4 to 12 digits."}), 400
    try:
        ctx.managers.set_pin(session["username"], current_pin, new_pin)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    ctx.logger.info("Manager PIN updated for %s", session["username"])
    return jsonify({"ok": True})


@manager_bp.route("/api/manager/accounts", methods=["GET"])
@require_manager
def get_manager_accounts():
    ctx = get_ctx()
    return jsonify({"ok": True, "managers": ctx.managers.public_accounts()})


@manager_bp.route("/api/manager/create-account", methods=["POST"])
@require_manager
def create_manager_account():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    full_name = str(payload.get("fullName") or "").strip()
    username = str(payload.get("username") or "").strip().lower()
    pin = str(payload.get("pin") or "").strip()
    if not full_name:
        return jsonify({"error": "Full name is required."}), 400
    if " " not in full_name:
        return jsonify({"error": "Full name must include first and last name."}), 400
    if not username or not username.replace("_", "").replace("-", "").isalnum():
        return jsonify({"error": "Username must use letters, numbers, dashes, or underscores."}), 400
    if not pin.isdigit() or not (4 <= len(pin) <= 12):
        return jsonify({"error": "PIN must be 4 to 12 digits."}), 400
    try:
        ctx.managers.create_account(full_name, username, pin)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    ctx.logger.info("Manager account created for %s", username)
    return jsonify({"ok": True})


@manager_bp.route("/api/manager/activity", methods=["GET"])
@require_manager
def manager_activity_list():
    ctx = get_ctx()
    return jsonify({"ok": True, "records": ctx.activity.read()[-120:]})


@manager_bp.route("/api/manager/activity", methods=["POST"])
@require_manager
def manager_activity_add():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    entry = sanitize_activity_entry(payload)
    if not entry:
        return jsonify({"ok": False, "error": "Message is required."}), 400
    session = request.manager_session
    entry["actor"] = str(session.get("fullName") or session.get("username") or entry["actor"])[:120]
    ctx.activity.append(entry)
    return jsonify({"ok": True, "record": entry})


@manager_bp.route("/api/manager/activity", methods=["PUT"])
@require_manager
def manager_activity_replace():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    incoming = payload.get("records")
    if not isinstance(incoming, list):
        return jsonify({"ok": False, "error": "records must be an array."}), 400
    sanitized = []
    for item in incoming:
        entry = sanitize_activity_entry(item)
        if entry:
            sanitized.append(entry)
    stored = ctx.activity.replace(sanitized)
    return jsonify({"ok": True, "count": len(stored)})


@manager_bp.route("/api/manager/activity", methods=["DELETE"])
@require_manager
def manager_activity_clear():
    get_ctx().activity.clear()
    return jsonify({"ok": True})


@manager_bp.route("/api/manager/tech-logins", methods=["GET"])
@require_manager
def list_tech_logins():
    ctx = get_ctx()
    state = ctx.shared_state.copy_for_client(include_credential_meta=True)
    logins = [
        {"tech": name, **meta}
        for name, meta in (state.get("credentialMeta") or {}).items()
    ]
    return jsonify({"ok": True, "logins": logins})


@manager_bp.route("/api/manager/tech-logins", methods=["POST"])
@require_manager
def upsert_tech_login():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    tech_name = str(payload.get("tech") or "").strip()
    identifier = str(payload.get("identifier") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not tech_name or not identifier or not password:
        return jsonify({"ok": False, "error": "Tech name, login ID, and password are required."}), 400
    if len(password) < 4 or len(password) > 128:
        return jsonify({"ok": False, "error": "Password must be 4 to 128 characters."}), 400
    try:
        ctx.shared_state.set_tech_login(tech_name, identifier, password, must_change=True)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify({"ok": True})


@manager_bp.route("/api/manager/tech-logins/password", methods=["POST"])
@require_manager
def reset_tech_password():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    tech_name = str(payload.get("tech") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not tech_name or not password:
        return jsonify({"ok": False, "error": "Tech name and password are required."}), 400
    if len(password) < 4 or len(password) > 128:
        return jsonify({"ok": False, "error": "Password must be 4 to 128 characters."}), 400
    ctx.shared_state.reset_tech_password(tech_name, password)
    return jsonify({"ok": True})


@manager_bp.route("/api/manager/tech-logins/delete", methods=["POST"])
@require_manager
def delete_tech_login():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    tech_name = str(payload.get("tech") or "").strip()
    if not tech_name:
        return jsonify({"ok": False, "error": "Tech name is required."}), 400
    removed = ctx.shared_state.delete_tech_login(tech_name)
    if removed:
        ctx.removed_logins[tech_name] = removed
    return jsonify({"ok": True})


@manager_bp.route("/api/manager/tech-logins/restore", methods=["POST"])
@require_manager
def restore_tech_login():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    tech_name = str(payload.get("tech") or "").strip()
    if not tech_name:
        return jsonify({"ok": False, "error": "Tech name is required."}), 400
    saved = ctx.removed_logins.pop(tech_name, None)
    ctx.shared_state.restore_tech_login(tech_name, saved)
    return jsonify({"ok": True})


@manager_bp.route("/api/manager/credentials/import", methods=["POST"])
@require_manager
def import_credentials():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    credentials = payload.get("credentials")
    if not isinstance(credentials, dict):
        return jsonify({"ok": False, "error": "credentials must be an object."}), 400
    count = ctx.shared_state.import_credentials(credentials)
    return jsonify({"ok": True, "count": count})
