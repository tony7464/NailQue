import time
import uuid

from flask import Blueprint, jsonify, request

from nailque.network import mobile_requires_lan, request_client_ip
from nailque.storage import (
    MOBILE_SESSION_TTL_SECONDS,
    MOBILE_SESSIONS,
    SERVICES_MENU,
    SHARED_STATE,
    SHARED_STATE_LOCK,
    append_service_history,
    build_service_details,
    cleanup_mobile_sessions,
    get_active_mobile_techs,
    persist_shared_state,
    read_service_history,
    safe_copy_shared_state,
    try_auto_assign_shared_state,
)

bp = Blueprint("mobile", __name__)


def _resolve_mobile_session():
    cleanup_mobile_sessions()
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.replace("Bearer ", "", 1).strip()
    session = MOBILE_SESSIONS.get(token)
    if not session:
        return None
    client_ip = request_client_ip()
    if session.get("ip") != client_ip:
        return None
    return session


@bp.route("/api/mobile/login", methods=["POST"])
def mobile_login():
    blocked = mobile_requires_lan()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    identifier = str(payload.get("identifier") or "").strip().lower()
    password = str(payload.get("password") or "")
    with SHARED_STATE_LOCK:
        credentials = dict(SHARED_STATE.get("credentials") or {})
    matched_tech = None
    for tech_name, cred in credentials.items():
        saved_identifier = str((cred or {}).get("identifier") or "").strip().lower()
        saved_password = str((cred or {}).get("password") or "")
        if identifier == saved_identifier and password == saved_password:
            matched_tech = tech_name
            break
    if not matched_tech:
        return jsonify({"ok": False, "error": "Invalid login credentials."}), 401
    token = uuid.uuid4().hex
    MOBILE_SESSIONS[token] = {
        "tech": matched_tech,
        "ip": request_client_ip(),
        "expiresAt": int(time.time()) + MOBILE_SESSION_TTL_SECONDS,
    }
    matched_cred = credentials.get(matched_tech) or {}
    return jsonify({
        "ok": True,
        "token": token,
        "tech": matched_tech,
        "mustChangePassword": bool(matched_cred.get("mustChangePassword")),
    })


@bp.route("/api/tech/change-password", methods=["POST"])
def employee_change_password():
    payload = request.get_json(silent=True) or {}
    identifier = str(payload.get("identifier") or "").strip().lower()
    current_password = str(payload.get("currentPassword") or "")
    new_password = str(payload.get("newPassword") or "").strip()
    if not identifier or not current_password or not new_password:
        return jsonify({"ok": False, "error": "Identifier, current password, and new password are required."}), 400
    if len(new_password) < 4:
        return jsonify({"ok": False, "error": "New password must be at least 4 characters."}), 400
    if new_password == current_password:
        return jsonify({"ok": False, "error": "New password must be different from current password."}), 400

    with SHARED_STATE_LOCK:
        credentials = dict(SHARED_STATE.get("credentials") or {})
        matched_tech = None
        for tech_name, cred in credentials.items():
            saved_identifier = str((cred or {}).get("identifier") or "").strip().lower()
            saved_password = str((cred or {}).get("password") or "")
            if identifier == saved_identifier and current_password == saved_password:
                matched_tech = tech_name
                break
        if not matched_tech:
            return jsonify({"ok": False, "error": "Current credentials are incorrect."}), 401
        credentials[matched_tech] = credentials.get(matched_tech) or {}
        credentials[matched_tech]["password"] = new_password
        credentials[matched_tech]["mustChangePassword"] = False
        SHARED_STATE["credentials"] = credentials
    persist_shared_state()
    return jsonify({"ok": True, "tech": matched_tech})


@bp.route("/api/mobile/state", methods=["GET"])
def mobile_state():
    blocked = mobile_requires_lan()
    if blocked:
        return blocked
    session = _resolve_mobile_session()
    if not session:
        return jsonify({"ok": False, "error": "Unauthorized."}), 401
    state = safe_copy_shared_state()
    techs = state.get("techs") or {}
    bonus_clock_ins = state.get("bonusClockIns") or {}
    bonus_order = [
        name for name in sorted(
            [
                name for name, details in techs.items()
                if str((details or {}).get("status") or "Offline") == "Available"
                and int(bonus_clock_ins.get(name) or 0) > 0
            ],
            key=lambda name: int(bonus_clock_ins.get(name) or (10**15)),
        )
    ]
    bonus_position_map = {name: idx + 1 for idx, name in enumerate(bonus_order)}
    bonus_current = bonus_order[0] if bonus_order else ""
    techs_overview = [
        {
            "name": name,
            "status": str((details or {}).get("status") or "Offline"),
            "current": str((details or {}).get("current") or ""),
            "startTime": (details or {}).get("startTime"),
            "hasBonusRound": bool(name == bonus_current),
            "bonusQueuePosition": int(bonus_position_map.get(name) or 0),
        }
        for name, details in techs.items()
    ]
    techs_overview.sort(key=lambda item: item["name"].lower())
    return jsonify({
        "ok": True,
        "tech": session.get("tech"),
        "techState": techs.get(session.get("tech")) or {},
        "mustChangePassword": bool(((state.get("credentials") or {}).get(session.get("tech")) or {}).get("mustChangePassword")),
        "waitingQueue": state.get("waitingQueue") or [],
        "techsOverview": techs_overview,
        "servicesMenu": SERVICES_MENU,
        "serviceHistory": read_service_history()[-80:],
    })


@bp.route("/api/mobile/change-password", methods=["POST"])
def mobile_change_password():
    blocked = mobile_requires_lan()
    if blocked:
        return blocked
    session = _resolve_mobile_session()
    if not session:
        return jsonify({"ok": False, "error": "Unauthorized."}), 401
    payload = request.get_json(silent=True) or {}
    current_password = str(payload.get("currentPassword") or "")
    new_password = str(payload.get("newPassword") or "").strip()
    if not current_password or not new_password:
        return jsonify({"ok": False, "error": "Current and new password are required."}), 400
    if len(new_password) < 4:
        return jsonify({"ok": False, "error": "New password must be at least 4 characters."}), 400
    if new_password == current_password:
        return jsonify({"ok": False, "error": "New password must be different from current password."}), 400

    tech_name = session.get("tech")
    with SHARED_STATE_LOCK:
        credentials = dict(SHARED_STATE.get("credentials") or {})
        current_cred = credentials.get(tech_name) or {}
        saved_password = str(current_cred.get("password") or "")
        if current_password != saved_password:
            return jsonify({"ok": False, "error": "Current password is incorrect."}), 401
        credentials[tech_name] = current_cred
        credentials[tech_name]["password"] = new_password
        credentials[tech_name]["mustChangePassword"] = False
        SHARED_STATE["credentials"] = credentials
    persist_shared_state()
    return jsonify({"ok": True})


@bp.route("/api/mobile/action", methods=["POST"])
def mobile_action():
    blocked = mobile_requires_lan()
    if blocked:
        return blocked
    session = _resolve_mobile_session()
    if not session:
        return jsonify({"ok": False, "error": "Unauthorized."}), 401
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    tech_name = session.get("tech")
    with SHARED_STATE_LOCK:
        techs = SHARED_STATE.get("techs") or {}
        tech = techs.get(tech_name)
        if not tech:
            return jsonify({"ok": False, "error": "Tech not found."}), 404
        now_ms = int(time.time() * 1000)
        if action == "clock_in":
            if tech.get("status") not in {"Busy", "Scheduled Appointment"}:
                tech["status"] = "Available"
                bonus_clock_ins = SHARED_STATE.get("bonusClockIns") or {}
                if not bonus_clock_ins.get(tech_name):
                    bonus_clock_ins[tech_name] = now_ms
                SHARED_STATE["bonusClockIns"] = bonus_clock_ins
        elif action == "break":
            if tech.get("status") == "Busy":
                return jsonify({"ok": False, "error": "Cannot start break while busy."}), 400
            tech["status"] = "On Break"
            tech["current"] = None
            tech["startTime"] = None
        elif action == "end_break":
            if tech.get("status") == "On Break":
                tech["status"] = "Available"
                bonus_clock_ins = SHARED_STATE.get("bonusClockIns") or {}
                if not bonus_clock_ins.get(tech_name):
                    bonus_clock_ins[tech_name] = now_ms
                SHARED_STATE["bonusClockIns"] = bonus_clock_ins
        elif action == "finish_customer":
            selected_indexes_raw = payload.get("selectedServiceIndexes") or []
            custom_addons = payload.get("customAddons") or []
            if not isinstance(selected_indexes_raw, list):
                return jsonify({"ok": False, "error": "Service selection is invalid."}), 400
            selected_indexes = [int(i) for i in selected_indexes_raw if isinstance(i, int)]
            details = build_service_details(selected_indexes, custom_addons)
            completed_customer_name = str(tech.get("current") or "Customer")
            completion_record = {
                "tech": tech_name,
                "customer": completed_customer_name,
                "selectedServiceIndexes": details["selectedServiceIndexes"],
                "selectedServices": details["selectedServices"],
                "customAddons": details["customAddons"],
                "total": details["total"],
                "employeeShare": details["employeeShare"],
                "completedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "mobile",
            }
            tech["earnings"] = round(float(tech.get("earnings") or 0) + details["employeeShare"], 2)
            tech["status"] = "Available"
            tech["current"] = None
            tech["startTime"] = None
            bonus_clock_ins = SHARED_STATE.get("bonusClockIns") or {}
            if not bonus_clock_ins.get(tech_name):
                bonus_clock_ins[tech_name] = now_ms
            SHARED_STATE["bonusClockIns"] = bonus_clock_ins
            append_service_history(completion_record)
        elif action == "unready":
            if tech.get("status") == "Busy":
                return jsonify({"ok": False, "error": "Cannot go unready while busy."}), 400
            tech["status"] = "Offline"
            tech["current"] = None
            tech["startTime"] = None
        else:
            return jsonify({"ok": False, "error": "Unsupported action."}), 400
        techs[tech_name] = tech
        SHARED_STATE["techs"] = techs
        try_auto_assign_shared_state(SHARED_STATE)
    persist_shared_state()
    return jsonify({"ok": True, "state": safe_copy_shared_state()})


@bp.route("/api/mobile/active-techs", methods=["GET"])
def mobile_active_techs():
    blocked = mobile_requires_lan()
    if blocked:
        return blocked
    return jsonify({"ok": True, "activeTechs": get_active_mobile_techs()})
