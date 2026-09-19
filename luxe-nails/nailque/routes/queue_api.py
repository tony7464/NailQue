"""Front-desk queue sync and service history."""

from __future__ import annotations

import time

from flask import Blueprint, jsonify, request

from nailque.catalog import build_service_details
from nailque.factory import get_ctx
from nailque.http import require_lan, require_manager

queue_bp = Blueprint("queue", __name__)


@queue_bp.route("/api/shared/sync", methods=["POST"])
@require_lan
def shared_sync():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    state = ctx.shared_state.apply_desk_sync(payload, allow_credential_bootstrap=True)
    return jsonify({"ok": True, "state": state})


@queue_bp.route("/api/shared/state", methods=["GET"])
@require_lan
def shared_state():
    ctx = get_ctx()
    return jsonify({"ok": True, "state": ctx.shared_state.copy_for_client()})


@queue_bp.route("/api/services/history", methods=["GET"])
@require_manager
def services_history():
    ctx = get_ctx()
    return jsonify({"ok": True, "records": ctx.service_history.read()[-200:]})


@queue_bp.route("/api/services/record", methods=["POST"])
@require_lan
def services_record():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    tech_name = str(payload.get("tech") or "").strip()
    customer_name = str(payload.get("customer") or "Customer").strip() or "Customer"
    selected_indexes = payload.get("selectedServiceIndexes") or []
    custom_addons = payload.get("customAddons") or []
    if not isinstance(selected_indexes, list):
        selected_indexes = []
    selected_indexes = [int(i) for i in selected_indexes if isinstance(i, int)]
    details = build_service_details(selected_indexes, custom_addons)
    completed_at = str(payload.get("completedAt") or "") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    source = str(payload.get("source") or "frontdesk")
    record = {
        "tech": tech_name,
        "customer": customer_name,
        "selectedServiceIndexes": details["selectedServiceIndexes"],
        "selectedServices": details["selectedServices"],
        "customAddons": details["customAddons"],
        "total": details["total"],
        "employeeShare": details["employeeShare"],
        "completedAt": completed_at,
        "source": source[:40],
    }
    ctx.service_history.append(record)
    return jsonify({"ok": True, "record": record})
