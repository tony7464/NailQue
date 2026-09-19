"""Front-desk queue mutations, live state, service history, and receipts."""

from __future__ import annotations

import time
import uuid

from flask import Blueprint, jsonify, request

from nailque.catalog import build_service_details
from nailque.factory import get_ctx
from nailque.http import optional_manager_session, require_lan, require_manager

queue_bp = Blueprint("queue", __name__)

MANAGER_ACTIONS = {"remove_tech", "restore_tech", "reassign", "status_override"}


def _build_receipt(ctx, tech_name: str, customer_name: str, details: dict, source: str) -> dict:
    completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record = {
        "receiptId": uuid.uuid4().hex,
        "salonName": ctx.salon.salon_name(),
        "tech": tech_name,
        "customer": customer_name,
        "selectedServiceIndexes": details["selectedServiceIndexes"],
        "selectedServices": details["selectedServices"],
        "customAddons": details["customAddons"],
        "total": details["total"],
        "employeeShare": details["employeeShare"],
        "commissionRate": details.get("commissionRate", ctx.salon.commission_rate()),
        "completedAt": completed_at,
        "source": source[:40],
    }
    ctx.service_history.append(record)
    return record


def _finish_payload(payload: dict) -> tuple[list[int], list]:
    selected_indexes = payload.get("selectedServiceIndexes") or []
    custom_addons = payload.get("customAddons") or []
    if not isinstance(selected_indexes, list):
        selected_indexes = []
    selected_indexes = [int(i) for i in selected_indexes if isinstance(i, int)]
    return selected_indexes, custom_addons


@queue_bp.route("/api/shared/sync", methods=["POST"])
@require_lan
def shared_sync():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    state = ctx.shared_state.apply_desk_sync(payload, allow_credential_bootstrap=True)
    return jsonify({
        "ok": True,
        "state": state,
        "ignored": ["techs", "waitingQueue", "bonusClockIns", "nextCustomerId"],
        "message": "Queue state is server-owned. Use /api/queue/action to mutate it.",
    })


@queue_bp.route("/api/shared/state", methods=["GET"])
@require_lan
def shared_state():
    ctx = get_ctx()
    today = time.strftime("%Y-%m-%d", time.gmtime())
    completed_today = sum(
        1 for record in ctx.service_history.read()
        if str(record.get("completedAt") or "").startswith(today)
    )
    return jsonify({
        "ok": True,
        "state": ctx.shared_state.copy_for_client(),
        "salon": ctx.salon.public(),
        "setupComplete": ctx.managers.is_setup_complete(),
        "completedToday": completed_today,
    })


@queue_bp.route("/api/queue/action", methods=["POST"])
@require_lan
def queue_action():
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    if action in MANAGER_ACTIONS:
        session = optional_manager_session()
        if not session:
            return jsonify({"error": "Unauthorized."}), 401
        request.manager_session = session  # noqa: SLF001

    receipt = None
    try:
        if action == "add_customer":
            state = ctx.shared_state.add_customer(
                payload.get("name"),
                requested_tech=str(payload.get("requestedTech") or ""),
                appointment_time=payload.get("appointmentTime"),
            )
        elif action == "remove_customer":
            state = ctx.shared_state.remove_customer(int(payload.get("id")))
        elif action == "skip_customer":
            state = ctx.shared_state.skip_customer(int(payload.get("id")))
        elif action == "upsert_tech":
            state = ctx.shared_state.upsert_tech(str(payload.get("name") or "").strip())
        elif action == "remove_tech":
            name = str(payload.get("name") or "").strip()
            removed = ctx.shared_state.delete_tech_login(name)
            if removed:
                ctx.removed_logins[name] = removed
            state = ctx.shared_state.remove_tech(name)
        elif action == "restore_tech":
            name = str(payload.get("name") or "").strip()
            snapshot = payload.get("tech") if isinstance(payload.get("tech"), dict) else None
            saved = ctx.removed_logins.pop(name, None)
            ctx.shared_state.restore_tech_login(name, saved)
            state = ctx.shared_state.restore_tech(name, snapshot)
        elif action in {"set_status", "status_override"}:
            return_customer = bool(payload.get("returnCustomer", True))
            state = ctx.shared_state.set_tech_status(
                str(payload.get("name") or "").strip(),
                str(payload.get("status") or "").strip(),
                return_customer=return_customer,
            )
        elif action == "reassign":
            state = ctx.shared_state.reassign_customer(
                str(payload.get("fromTech") or "").strip(),
                str(payload.get("toTech") or "").strip(),
            )
        elif action == "skip_turn":
            state = ctx.shared_state.skip_turn(str(payload.get("name") or "").strip())
        elif action == "finish":
            tech_name = str(payload.get("name") or payload.get("tech") or "").strip()
            selected_indexes, custom_addons = _finish_payload(payload)
            details = build_service_details(
                selected_indexes,
                custom_addons,
                services=ctx.salon.services(),
                commission_rate=ctx.salon.commission_rate(),
            )
            state, customer_name = ctx.shared_state.finish_service(tech_name, details)
            receipt = _build_receipt(ctx, tech_name, customer_name, details, str(payload.get("source") or "frontdesk"))
        elif action == "add_appointment":
            state = ctx.shared_state.add_appointment(
                payload.get("name"),
                payload.get("appointmentTime"),
                requested_tech=str(payload.get("requestedTech") or ""),
                notes=str(payload.get("notes") or ""),
            )
        elif action == "arrive_appointment":
            state = ctx.shared_state.arrive_appointment(int(payload.get("id")))
        elif action == "cancel_appointment":
            state = ctx.shared_state.cancel_appointment(int(payload.get("id")))
        else:
            return jsonify({"ok": False, "error": "Unsupported action."}), 400
    except (TypeError, ValueError) as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    response = {"ok": True, "state": state}
    if receipt:
        response["receipt"] = receipt
    return jsonify(response)


@queue_bp.route("/api/services/history", methods=["GET"])
@require_manager
def services_history():
    ctx = get_ctx()
    return jsonify({"ok": True, "records": ctx.service_history.read()[-200:]})


@queue_bp.route("/api/services/record", methods=["POST"])
@require_lan
def services_record():
    """Legacy desk hook. Prefer action=finish so the server owns earnings and receipts."""
    ctx = get_ctx()
    payload = request.get_json(silent=True) or {}
    tech_name = str(payload.get("tech") or "").strip()
    customer_name = str(payload.get("customer") or "Customer").strip() or "Customer"
    selected_indexes, custom_addons = _finish_payload(payload)
    details = build_service_details(
        selected_indexes,
        custom_addons,
        services=ctx.salon.services(),
        commission_rate=ctx.salon.commission_rate(),
    )
    record = _build_receipt(ctx, tech_name, customer_name, details, str(payload.get("source") or "frontdesk"))
    return jsonify({"ok": True, "record": record, "receipt": record})


@queue_bp.route("/api/receipts/<receipt_id>", methods=["GET"])
@require_lan
def get_receipt(receipt_id: str):
    ctx = get_ctx()
    wanted = str(receipt_id or "").strip()
    for record in reversed(ctx.service_history.read()):
        if str(record.get("receiptId") or "") == wanted:
            return jsonify({"ok": True, "receipt": record})
    return jsonify({"ok": False, "error": "Receipt was not found."}), 404
