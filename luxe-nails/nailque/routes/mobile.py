"""Mobile tech login, status, and ticket actions."""

from __future__ import annotations

import time
import uuid

from flask import Blueprint, jsonify, request

from nailque.catalog import build_service_details
from nailque.factory import get_ctx
from nailque.http import client_ip, rate_limited, require_lan, require_manager, require_mobile

mobile_bp = Blueprint("mobile", __name__)


def _bonus_overview(state: dict) -> list[dict]:
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
    overview = [
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
    overview.sort(key=lambda item: item["name"].lower())
    return overview


@mobile_bp.route("/api/mobile/login", methods=["POST"])
@require_lan
@rate_limited("mobile-login", limit=8, window_seconds=300)
def mobile_login():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    identifier = str(payload.get("identifier") or "").strip().lower()
    password = str(payload.get("password") or "")
    tech_name, cred = ctx.shared_state.authenticate_tech(identifier, password)
    if not tech_name or cred is None:
        return jsonify({"ok": False, "error": "Invalid login credentials."}), 401
    token = ctx.mobile_sessions.create({"tech": tech_name}, client_ip())
    return jsonify({
        "ok": True,
        "token": token,
        "tech": tech_name,
        "mustChangePassword": bool(cred.get("mustChangePassword")),
    })


@mobile_bp.route("/api/mobile/state", methods=["GET"])
@require_lan
@require_mobile
def mobile_state():
    ctx = get_ctx()
    session = request.mobile_session
    state = ctx.shared_state.copy_for_client(include_credential_meta=True)
    techs = state.get("techs") or {}
    tech_name = session.get("tech")
    history = [
        record for record in ctx.service_history.read()[-80:]
        if record.get("tech") == tech_name
    ]
    cred_meta = (state.get("credentialMeta") or {}).get(tech_name) or {}
    return jsonify({
        "ok": True,
        "tech": tech_name,
        "techState": techs.get(tech_name) or {},
        "mustChangePassword": bool(cred_meta.get("mustChangePassword")),
        "waitingQueue": state.get("waitingQueue") or [],
        "techsOverview": _bonus_overview(state),
        "servicesMenu": ctx.salon.services(),
        "commissionRate": ctx.salon.commission_rate(),
        "salonName": ctx.salon.salon_name(),
        "serviceHistory": history,
    })


@mobile_bp.route("/api/mobile/change-password", methods=["POST"])
@require_lan
@require_mobile
def mobile_change_password():
    ctx = get_ctx()
    session = request.mobile_session
    payload = request.get_json(silent=True) or {}
    current_password = str(payload.get("currentPassword") or "")
    new_password = str(payload.get("newPassword") or "").strip()
    if not current_password or not new_password:
        return jsonify({"ok": False, "error": "Current and new password are required."}), 400
    if len(new_password) < 4 or len(new_password) > 128:
        return jsonify({"ok": False, "error": "New password must be 4 to 128 characters."}), 400
    if new_password == current_password:
        return jsonify({"ok": False, "error": "New password must be different from current password."}), 400
    try:
        ctx.shared_state.update_tech_password(session.get("tech"), current_password, new_password)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 401
    return jsonify({"ok": True})


@mobile_bp.route("/api/mobile/action", methods=["POST"])
@require_lan
@require_mobile
def mobile_action():
    ctx = get_ctx()
    session = request.mobile_session
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    tech_name = session.get("tech")
    completion_record = None
    with ctx.shared_state.lock:
        techs = ctx.shared_state.state.get("techs") or {}
        tech = techs.get(tech_name)
        if not tech:
            return jsonify({"ok": False, "error": "Tech not found."}), 404
        now_ms = int(time.time() * 1000)
        if action == "clock_in":
            if tech.get("status") not in {"Busy", "Scheduled Appointment"}:
                tech["status"] = "Available"
                bonus_clock_ins = ctx.shared_state.state.get("bonusClockIns") or {}
                if not bonus_clock_ins.get(tech_name):
                    bonus_clock_ins[tech_name] = now_ms
                ctx.shared_state.state["bonusClockIns"] = bonus_clock_ins
        elif action == "break":
            if tech.get("status") == "Busy":
                return jsonify({"ok": False, "error": "Cannot start break while busy."}), 400
            tech["status"] = "On Break"
            tech["current"] = None
            tech["startTime"] = None
        elif action == "end_break":
            if tech.get("status") == "On Break":
                tech["status"] = "Available"
                bonus_clock_ins = ctx.shared_state.state.get("bonusClockIns") or {}
                if not bonus_clock_ins.get(tech_name):
                    bonus_clock_ins[tech_name] = now_ms
                ctx.shared_state.state["bonusClockIns"] = bonus_clock_ins
        elif action == "finish_customer":
            selected_indexes_raw = payload.get("selectedServiceIndexes") or []
            custom_addons = payload.get("customAddons") or []
            if not isinstance(selected_indexes_raw, list):
                return jsonify({"ok": False, "error": "Service selection is invalid."}), 400
            selected_indexes = [int(i) for i in selected_indexes_raw if isinstance(i, int)]
            details = build_service_details(
                selected_indexes,
                custom_addons,
                services=ctx.salon.services(),
                commission_rate=ctx.salon.commission_rate(),
            )
            completed_customer_name = str(tech.get("current") or "Customer")
            completion_record = {
                "receiptId": uuid.uuid4().hex,
                "salonName": ctx.salon.salon_name(),
                "tech": tech_name,
                "customer": completed_customer_name,
                "selectedServiceIndexes": details["selectedServiceIndexes"],
                "selectedServices": details["selectedServices"],
                "customAddons": details["customAddons"],
                "total": details["total"],
                "employeeShare": details["employeeShare"],
                "commissionRate": details.get("commissionRate", ctx.salon.commission_rate()),
                "completedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "mobile",
            }
            tech["earnings"] = round(float(tech.get("earnings") or 0) + details["employeeShare"], 2)
            tech["status"] = "Available"
            tech["current"] = None
            tech["startTime"] = None
            bonus_clock_ins = ctx.shared_state.state.get("bonusClockIns") or {}
            if not bonus_clock_ins.get(tech_name):
                bonus_clock_ins[tech_name] = now_ms
            ctx.shared_state.state["bonusClockIns"] = bonus_clock_ins
        elif action == "unready":
            if tech.get("status") == "Busy":
                return jsonify({"ok": False, "error": "Cannot go unready while busy."}), 400
            tech["status"] = "Offline"
            tech["current"] = None
            tech["startTime"] = None
        else:
            return jsonify({"ok": False, "error": "Unsupported action."}), 400
        techs[tech_name] = tech
        ctx.shared_state.state["techs"] = techs
        from nailque.queue import try_auto_assign

        try_auto_assign(ctx.shared_state.state)
    if completion_record:
        ctx.service_history.append(completion_record)
    ctx.shared_state.persist()
    payload = {"ok": True, "state": ctx.shared_state.copy_for_client()}
    if completion_record:
        payload["receipt"] = completion_record
    return jsonify(payload)


@mobile_bp.route("/api/mobile/active-techs", methods=["GET"])
@require_manager
def mobile_active_techs():
    ctx = get_ctx()
    now = int(time.time())
    active = {}
    for session in ctx.mobile_sessions.active_payloads():
        tech_name = str(session.get("tech") or "")
        if not tech_name:
            continue
        active[tech_name] = {
            "tech": tech_name,
            "ip": str(session.get("ip") or ""),
            "expiresInSeconds": max(0, int(session.get("expiresAt") or 0) - now),
        }
    return jsonify({"ok": True, "activeTechs": list(active.values())})
