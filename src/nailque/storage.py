import json
import os
import threading
import time
from pathlib import Path

from nailque.config import MANAGER_ACTIVITY_FILE, SERVICE_HISTORY_FILE, SHARED_STATE_FILE

SHARED_STATE_LOCK = threading.Lock()
SHARED_STATE = {}
MOBILE_SESSIONS = {}
MOBILE_SESSION_TTL_SECONDS = 12 * 60 * 60
SERVICES_MENU = [
    {"name": "Spa Manicure", "price": 40},
    {"name": "Signature Manicure", "price": 50},
    {"name": "Ultimate M.V. Spa Manicure", "price": 65},
    {"name": "Spa Pedicure", "price": 60},
    {"name": "Signature Pedicure", "price": 70},
    {"name": "Full Set Acrylic", "price": 55},
    {"name": "Fill", "price": 40},
    {"name": "Gel Polish", "price": 25},
    {"name": "Polish Change", "price": 15},
    {"name": "Nail Art (per nail)", "price": 5},
    {"name": "Coffin / Stiletto Shape (+$5)", "price": 5},
    {"name": "Almond / Ballerina Shape (+$5)", "price": 5},
    {"name": "Paraffin Treatment", "price": 15},
    {"name": "Sugar Scrub", "price": 10},
    {"name": "Collagen Gloves", "price": 20},
    {"name": "Hot Stone Massage", "price": 15},
]


def empty_shared_state():
    return {
        "techs": {},
        "waitingQueue": [],
        "nextCustomerId": 1,
        "bonusClockIns": {},
        "credentials": {},
        "updatedAt": int(time.time()),
    }


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return fallback


def write_json_atomic(path: Path, payload):
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    os.replace(temp_path, path)


def load_shared_state():
    global SHARED_STATE
    saved = read_json(SHARED_STATE_FILE, empty_shared_state())
    if not isinstance(saved, dict):
        saved = empty_shared_state()
    for key, fallback in empty_shared_state().items():
        if key not in saved:
            saved[key] = fallback
    SHARED_STATE = saved


def persist_shared_state():
    with SHARED_STATE_LOCK:
        SHARED_STATE["updatedAt"] = int(time.time())
        write_json_atomic(SHARED_STATE_FILE, SHARED_STATE)


def safe_copy_shared_state():
    with SHARED_STATE_LOCK:
        return {
            "techs": dict(SHARED_STATE.get("techs") or {}),
            "waitingQueue": list(SHARED_STATE.get("waitingQueue") or []),
            "nextCustomerId": int(SHARED_STATE.get("nextCustomerId") or 1),
            "bonusClockIns": dict(SHARED_STATE.get("bonusClockIns") or {}),
            "credentials": dict(SHARED_STATE.get("credentials") or {}),
            "updatedAt": int(SHARED_STATE.get("updatedAt") or 0),
        }


def cleanup_mobile_sessions():
    now = int(time.time())
    expired = [token for token, item in MOBILE_SESSIONS.items() if int(item.get("expiresAt") or 0) <= now]
    for token in expired:
        MOBILE_SESSIONS.pop(token, None)


def get_active_mobile_techs():
    cleanup_mobile_sessions()
    active = {}
    now = int(time.time())
    for session in MOBILE_SESSIONS.values():
        tech_name = str(session.get("tech") or "")
        if not tech_name:
            continue
        active[tech_name] = {
            "tech": tech_name,
            "ip": str(session.get("ip") or ""),
            "expiresInSeconds": max(0, int(session.get("expiresAt") or 0) - now),
        }
    return list(active.values())


def get_available_tech_order(state):
    techs = state.get("techs") or {}
    bonus_clock_ins = state.get("bonusClockIns") or {}
    return sorted(
        [name for name, details in techs.items() if details.get("status") == "Available"],
        key=lambda name: int(bonus_clock_ins.get(name) or (10**15)),
    )


def try_auto_assign_shared_state(state):
    techs = state.get("techs") or {}
    queue = state.get("waitingQueue") or []
    bonus_clock_ins = state.get("bonusClockIns") or {}
    if not queue:
        return
    now_ms = int(time.time() * 1000)

    def assignable_index(tech_name):
        for idx, customer in enumerate(queue):
            appointment_time = customer.get("appointmentTime")
            requested = customer.get("requestedTech") or ""
            appointment_ready = not appointment_time or int(appointment_time) <= now_ms
            matches = (not requested) or (requested == tech_name)
            if appointment_ready and matches:
                return idx
        return -1

    while True:
        available_order = get_available_tech_order(state)
        if not available_order or not queue:
            break
        assigned = False
        for tech_name in available_order:
            idx = assignable_index(tech_name)
            if idx < 0:
                continue
            customer = queue.pop(idx)
            tech = techs.get(tech_name) or {}
            tech["status"] = "Busy"
            tech["current"] = customer.get("name") or "Customer"
            tech["startTime"] = now_ms
            techs[tech_name] = tech
            assigned = True
            break
        if not assigned:
            break
    state["techs"] = techs
    state["waitingQueue"] = queue
    state["bonusClockIns"] = bonus_clock_ins


def read_service_history():
    records = read_json(SERVICE_HISTORY_FILE, [])
    if not isinstance(records, list):
        return []
    return records


def append_service_history(record):
    records = read_service_history()
    records.append(record)
    records = records[-1000:]
    write_json_atomic(SERVICE_HISTORY_FILE, records)


def read_manager_activity():
    records = read_json(MANAGER_ACTIVITY_FILE, [])
    if not isinstance(records, list):
        return []
    return records


def append_manager_activity(record):
    records = read_manager_activity()
    records.append(record)
    records = records[-300:]
    write_json_atomic(MANAGER_ACTIVITY_FILE, records)


def clear_manager_activity():
    write_json_atomic(MANAGER_ACTIVITY_FILE, [])


def sanitize_manager_activity_entry(payload):
    if not isinstance(payload, dict):
        return None
    message = str(payload.get("message") or "").strip()
    if not message:
        return None
    actor = str(payload.get("actor") or "Manager").strip() or "Manager"
    level = str(payload.get("level") or "info").strip().lower()
    timestamp = str(payload.get("timestamp") or "").strip() or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if level not in {"info", "success", "error"}:
        level = "info"
    return {
        "message": message[:500],
        "actor": actor[:120],
        "level": level,
        "timestamp": timestamp,
    }


def build_service_details(selected_service_indexes, custom_addons=None):
    total = 0.0
    selected_indexes = []
    selected_services = []
    normalized_addons = []
    for idx in selected_service_indexes:
        if not isinstance(idx, int):
            continue
        if idx < 0 or idx >= len(SERVICES_MENU):
            continue
        selected_indexes.append(idx)
        svc = SERVICES_MENU[idx]
        selected_services.append(svc["name"])
        total += float(svc["price"])
    if isinstance(custom_addons, list):
        for addon in custom_addons:
            if not isinstance(addon, dict):
                continue
            name = str(addon.get("name") or "").strip()
            if not name:
                continue
            try:
                price = round(float(addon.get("price") or 0), 2)
            except (TypeError, ValueError):
                continue
            if price < 0:
                continue
            normalized_addons.append({"name": name[:80], "price": price})
            selected_services.append(f"{name[:80]} (Add-on)")
            total += price
    total = round(total, 2)
    return {
        "selectedServiceIndexes": selected_indexes,
        "selectedServices": selected_services,
        "customAddons": normalized_addons,
        "total": total,
        "employeeShare": round(total * 0.6, 2),
    }


load_shared_state()
