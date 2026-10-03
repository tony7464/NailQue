from flask import Blueprint, current_app, jsonify, request

from nailque.config import MANAGER_ACTIVITY_FILE
from nailque.managers import (
    create_manager_account,
    find_manager,
    get_manager_accounts,
    get_manager_pin,
    set_manager_pin,
)
from nailque.storage import (
    append_manager_activity,
    clear_manager_activity,
    read_manager_activity,
    sanitize_manager_activity_entry,
    write_json_atomic,
)

bp = Blueprint("manager", __name__)


@bp.route("/api/manager/verify-pin", methods=["POST"])
def verify_manager_pin():
    payload = request.get_json(silent=True) or {}
    entered = str(payload.get("pin") or "")
    username = str(payload.get("username") or "").strip().lower()
    manager = find_manager(username, entered)
    if not manager and entered == get_manager_pin():
        manager = get_manager_accounts()[0]
    if not manager:
        return jsonify({"ok": False})
    return jsonify({"ok": True, "manager": {"username": manager["username"], "fullName": manager["fullName"]}})


@bp.route("/api/manager/set-pin", methods=["POST"])
def update_manager_pin():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip().lower()
    current_pin = str(payload.get("currentPin") or "")
    new_pin = str(payload.get("newPin") or "")

    manager = find_manager(username, current_pin)
    if not manager:
        return jsonify({"error": "Current PIN is incorrect."}), 400
    if not new_pin.isdigit() or len(new_pin) < 4:
        return jsonify({"error": "New PIN must be at least 4 digits."}), 400

    set_manager_pin(username, new_pin)
    current_app.logger.info("Manager PIN updated for %s", username)
    return jsonify({"ok": True})


@bp.route("/api/manager/accounts", methods=["GET"])
def manager_accounts():
    managers = [{"username": m["username"], "fullName": m["fullName"]} for m in get_manager_accounts()]
    return jsonify({"ok": True, "managers": managers})


@bp.route("/api/manager/create-account", methods=["POST"])
def create_account():
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
    if not pin.isdigit() or len(pin) < 4:
        return jsonify({"error": "PIN must be at least 4 digits."}), 400
    try:
        create_manager_account(full_name, username, pin)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    current_app.logger.info("Manager account created for %s", username)
    return jsonify({"ok": True})


@bp.route("/api/manager/activity", methods=["GET"])
def manager_activity_list():
    records = read_manager_activity()
    return jsonify({"ok": True, "records": records[-120:]})


@bp.route("/api/manager/activity", methods=["POST"])
def manager_activity_add():
    payload = request.get_json(silent=True) or {}
    entry = sanitize_manager_activity_entry(payload)
    if not entry:
        return jsonify({"ok": False, "error": "Message is required."}), 400
    append_manager_activity(entry)
    return jsonify({"ok": True, "record": entry})


@bp.route("/api/manager/activity", methods=["PUT"])
def manager_activity_replace():
    payload = request.get_json(silent=True) or {}
    incoming = payload.get("records")
    if not isinstance(incoming, list):
        return jsonify({"ok": False, "error": "records must be an array."}), 400
    sanitized = []
    for item in incoming:
        entry = sanitize_manager_activity_entry(item)
        if entry:
            sanitized.append(entry)
    sanitized = sanitized[-300:]
    write_json_atomic(MANAGER_ACTIVITY_FILE, sanitized)
    return jsonify({"ok": True, "count": len(sanitized)})


@bp.route("/api/manager/activity", methods=["DELETE"])
def manager_activity_clear():
    clear_manager_activity()
    return jsonify({"ok": True})
