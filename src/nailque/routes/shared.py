import os
import time

from flask import Blueprint, jsonify, request

from nailque.config import APP_VERSION, RUNTIME_DIR
from nailque.network import detect_lan_ip, qr_png_data_url
from nailque.storage import (
    SHARED_STATE,
    SHARED_STATE_LOCK,
    append_service_history,
    build_service_details,
    persist_shared_state,
    read_service_history,
    safe_copy_shared_state,
    try_auto_assign_shared_state,
)

bp = Blueprint("shared", __name__)


@bp.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "nailque",
        "version": APP_VERSION,
        "runtime_dir": str(RUNTIME_DIR),
    })


@bp.route("/api/network-info", methods=["GET"])
def network_info():
    lan_ip = detect_lan_ip()
    port = int(os.getenv("PORT", "5001"))
    mobile_url = f"http://{lan_ip}:{port}/mobile"
    return jsonify({
        "ok": True,
        "lan_ip": lan_ip,
        "mobile_url": mobile_url,
        "mobile_qr_data_url": qr_png_data_url(mobile_url),
    })


@bp.route("/api/shared/sync", methods=["POST"])
def shared_sync():
    payload = request.get_json(silent=True) or {}
    with SHARED_STATE_LOCK:
        if isinstance(payload.get("techs"), dict):
            SHARED_STATE["techs"] = payload.get("techs")
        if isinstance(payload.get("waitingQueue"), list):
            SHARED_STATE["waitingQueue"] = payload.get("waitingQueue")
        if isinstance(payload.get("bonusClockIns"), dict):
            SHARED_STATE["bonusClockIns"] = payload.get("bonusClockIns")
        if isinstance(payload.get("credentials"), dict):
            SHARED_STATE["credentials"] = payload.get("credentials")
        if isinstance(payload.get("nextCustomerId"), int):
            SHARED_STATE["nextCustomerId"] = payload.get("nextCustomerId")
        try_auto_assign_shared_state(SHARED_STATE)
    persist_shared_state()
    return jsonify({"ok": True, "state": safe_copy_shared_state()})


@bp.route("/api/shared/state", methods=["GET"])
def shared_state():
    return jsonify({"ok": True, "state": safe_copy_shared_state()})


@bp.route("/api/services/history", methods=["GET"])
def services_history():
    records = read_service_history()
    return jsonify({"ok": True, "records": records[-200:]})


@bp.route("/api/services/record", methods=["POST"])
def services_record():
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
        "source": source,
    }
    append_service_history(record)
    return jsonify({"ok": True, "record": record})
