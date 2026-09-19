"""Shared front-desk queue state and automatic assignment."""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any

from nailque.security import hash_secret, is_hashed_secret, verify_secret
from nailque.storage import read_json, write_json_atomic

ALLOWED_STATUSES = {
    "Offline",
    "Available",
    "Busy",
    "On Break",
    "Scheduled Appointment",
}


def empty_shared_state() -> dict[str, Any]:
    return {
        "techs": {},
        "waitingQueue": [],
        "appointments": [],
        "nextCustomerId": 1,
        "nextAppointmentId": 1,
        "bonusClockIns": {},
        "credentials": {},
        "updatedAt": int(time.time()),
    }


def public_credential_meta(credentials: dict | None) -> dict[str, dict[str, Any]]:
    meta = {}
    for name, cred in (credentials or {}).items():
        if not isinstance(cred, dict):
            continue
        meta[str(name)] = {
            "identifier": str(cred.get("identifier") or "").strip(),
            "mustChangePassword": bool(cred.get("mustChangePassword")),
        }
    return meta


def sanitize_state_for_client(state: dict[str, Any], include_credential_meta: bool = False) -> dict[str, Any]:
    payload = {
        "techs": deepcopy(state.get("techs") or {}),
        "waitingQueue": deepcopy(state.get("waitingQueue") or []),
        "appointments": deepcopy(state.get("appointments") or []),
        "nextCustomerId": int(state.get("nextCustomerId") or 1),
        "nextAppointmentId": int(state.get("nextAppointmentId") or 1),
        "bonusClockIns": deepcopy(state.get("bonusClockIns") or {}),
        "updatedAt": int(state.get("updatedAt") or 0),
        "credentialsConfigured": bool(state.get("credentials")),
    }
    if include_credential_meta:
        payload["credentialMeta"] = public_credential_meta(state.get("credentials") or {})
    return payload


def _now_ms() -> int:
    return int(time.time() * 1000)


def available_tech_order(state: dict[str, Any]) -> list[str]:
    techs = state.get("techs") or {}
    bonus_clock_ins = state.get("bonusClockIns") or {}
    return sorted(
        [name for name, details in techs.items() if (details or {}).get("status") == "Available"],
        key=lambda name: int(bonus_clock_ins.get(name) or (10**15)),
    )


def try_auto_assign(state: dict[str, Any]) -> None:
    techs = state.get("techs") or {}
    queue = state.get("waitingQueue") or []
    if not queue:
        return
    now_ms = _now_ms()

    def assignable_index(tech_name: str) -> int:
        for idx, customer in enumerate(queue):
            appointment_time = customer.get("appointmentTime")
            requested = customer.get("requestedTech") or ""
            appointment_ready = not appointment_time or int(appointment_time) <= now_ms
            matches = (not requested) or (requested == tech_name)
            if appointment_ready and matches:
                return idx
        return -1

    while True:
        order = available_tech_order(state)
        if not order or not queue:
            break
        assigned = False
        for tech_name in order:
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


def hash_credential_map(raw_credentials: dict | None) -> dict[str, dict[str, Any]]:
    hashed = {}
    if not isinstance(raw_credentials, dict):
        return hashed
    for tech_name, cred in raw_credentials.items():
        if not isinstance(cred, dict):
            continue
        identifier = str(cred.get("identifier") or "").strip()
        password = str(cred.get("password") or "")
        if not identifier:
            continue
        stored = password
        if password and not is_hashed_secret(password):
            stored = hash_secret(password)
        hashed[str(tech_name)] = {
            "identifier": identifier,
            "password": stored,
            "mustChangePassword": bool(cred.get("mustChangePassword")),
        }
    return hashed


def find_tech_by_login(credentials: dict, identifier: str, password: str) -> tuple[str | None, dict | None, bool]:
    wanted = str(identifier or "").strip().lower()
    for tech_name, cred in (credentials or {}).items():
        if not isinstance(cred, dict):
            continue
        saved_identifier = str(cred.get("identifier") or "").strip().lower()
        if saved_identifier != wanted:
            continue
        matched, needs_rehash = verify_secret(str(cred.get("password") or ""), password)
        if matched:
            return str(tech_name), dict(cred), needs_rehash
    return None, None, False


def _blank_tech() -> dict[str, Any]:
    return {"status": "Offline", "current": None, "startTime": None, "earnings": 0}


def _ensure_tech(state: dict[str, Any], name: str) -> dict[str, Any]:
    techs = state.setdefault("techs", {})
    tech = techs.get(name)
    if not isinstance(tech, dict):
        tech = _blank_tech()
        techs[name] = tech
    tech.setdefault("status", "Offline")
    tech.setdefault("current", None)
    tech.setdefault("startTime", None)
    tech.setdefault("earnings", 0)
    return tech


def _return_customer_to_queue(state: dict[str, Any], customer_name: str) -> None:
    if not customer_name:
        return
    queue = state.setdefault("waitingQueue", [])
    next_id = int(state.get("nextCustomerId") or 1)
    queue.insert(0, {
        "id": next_id,
        "name": customer_name,
        "arrival": _now_ms(),
        "requestedTech": "",
        "appointmentTime": None,
    })
    state["nextCustomerId"] = next_id + 1
    state["waitingQueue"] = queue


class SharedStateStore:
    def __init__(self, state_file):
        self.state_file = state_file
        self.lock = threading.RLock()
        self.state = empty_shared_state()
        self._credentials_bootstrapped = False
        self.load()

    def load(self) -> None:
        saved = read_json(self.state_file, empty_shared_state())
        if not isinstance(saved, dict):
            saved = empty_shared_state()
        merged = empty_shared_state()
        merged.update({key: saved[key] for key in merged if key in saved})
        if not isinstance(merged.get("techs"), dict):
            merged["techs"] = {}
        if not isinstance(merged.get("waitingQueue"), list):
            merged["waitingQueue"] = []
        if not isinstance(merged.get("appointments"), list):
            merged["appointments"] = []
        if not isinstance(merged.get("bonusClockIns"), dict):
            merged["bonusClockIns"] = {}
        merged["credentials"] = hash_credential_map(merged.get("credentials") or {})
        self.state = merged
        self._credentials_bootstrapped = bool(self.state.get("credentials"))
        self.persist()

    def persist(self) -> None:
        with self.lock:
            self.state["updatedAt"] = int(time.time())
            write_json_atomic(self.state_file, self.state)

    def copy_for_client(self, include_credential_meta: bool = False) -> dict[str, Any]:
        with self.lock:
            return sanitize_state_for_client(self.state, include_credential_meta=include_credential_meta)

    def apply_desk_sync(self, payload: dict[str, Any], allow_credential_bootstrap: bool = False) -> dict[str, Any]:
        """Legacy full-state POST. Queue/techs are server-owned and are not replaced."""
        with self.lock:
            incoming_credentials = payload.get("credentials")
            if (
                allow_credential_bootstrap
                and not self._credentials_bootstrapped
                and isinstance(incoming_credentials, dict)
                and incoming_credentials
            ):
                self.state["credentials"] = hash_credential_map(incoming_credentials)
                self._credentials_bootstrapped = True
            try_auto_assign(self.state)
        self.persist()
        return self.copy_for_client()

    def add_customer(self, name: str, requested_tech: str = "", appointment_time=None) -> dict[str, Any]:
        clean_name = str(name or "").strip()[:80]
        if not clean_name:
            raise ValueError("Customer name is required.")
        requested = str(requested_tech or "").strip()
        appt = None
        if appointment_time not in (None, "", 0):
            try:
                appt = int(appointment_time)
            except (TypeError, ValueError) as error:
                raise ValueError("Appointment time is invalid.") from error
        with self.lock:
            if requested and requested not in (self.state.get("techs") or {}):
                raise ValueError("Requested tech was not found.")
            customer_id = int(self.state.get("nextCustomerId") or 1)
            self.state.setdefault("waitingQueue", []).append({
                "id": customer_id,
                "name": clean_name,
                "arrival": _now_ms(),
                "requestedTech": requested,
                "appointmentTime": appt,
            })
            self.state["nextCustomerId"] = customer_id + 1
            try_auto_assign(self.state)
        self.persist()
        return self.copy_for_client()

    def remove_customer(self, customer_id: int) -> dict[str, Any]:
        with self.lock:
            queue = self.state.get("waitingQueue") or []
            remaining = [item for item in queue if int(item.get("id") or 0) != int(customer_id)]
            if len(remaining) == len(queue):
                raise ValueError("Customer was not found in the waiting queue.")
            self.state["waitingQueue"] = remaining
        self.persist()
        return self.copy_for_client()

    def skip_customer(self, customer_id: int) -> dict[str, Any]:
        with self.lock:
            queue = list(self.state.get("waitingQueue") or [])
            idx = next((i for i, item in enumerate(queue) if int(item.get("id") or 0) == int(customer_id)), -1)
            if idx < 0:
                raise ValueError("Customer was not found in the waiting queue.")
            customer = queue.pop(idx)
            queue.append(customer)
            self.state["waitingQueue"] = queue
            try_auto_assign(self.state)
        self.persist()
        return self.copy_for_client()

    def upsert_tech(self, name: str) -> dict[str, Any]:
        clean = str(name or "").strip()
        if not clean:
            raise ValueError("Tech name is required.")
        with self.lock:
            _ensure_tech(self.state, clean)
        self.persist()
        return self.copy_for_client()

    def remove_tech(self, name: str) -> dict[str, Any]:
        with self.lock:
            techs = dict(self.state.get("techs") or {})
            if name not in techs:
                raise ValueError("Tech was not found.")
            if len(techs) <= 1:
                raise ValueError("You must keep at least one active tech account.")
            tech = techs.pop(name)
            if (tech or {}).get("status") == "Busy" and tech.get("current"):
                _return_customer_to_queue(self.state, str(tech.get("current")))
            bonus = dict(self.state.get("bonusClockIns") or {})
            bonus.pop(name, None)
            self.state["techs"] = techs
            self.state["bonusClockIns"] = bonus
            try_auto_assign(self.state)
        self.persist()
        return self.copy_for_client()

    def restore_tech(self, name: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.lock:
            techs = dict(self.state.get("techs") or {})
            restored = dict(snapshot or _blank_tech())
            restored.setdefault("status", "Offline")
            restored.setdefault("current", None)
            restored.setdefault("startTime", None)
            restored.setdefault("earnings", 0)
            techs[name] = restored
            self.state["techs"] = techs
        self.persist()
        return self.copy_for_client()

    def set_tech_status(self, name: str, status: str, return_customer: bool = True) -> dict[str, Any]:
        if status not in ALLOWED_STATUSES:
            raise ValueError("Unsupported tech status.")
        with self.lock:
            tech = (self.state.get("techs") or {}).get(name)
            if not tech:
                raise ValueError("Tech was not found.")
            now_ms = _now_ms()
            previous = str(tech.get("status") or "Offline")
            current_customer = str(tech.get("current") or "")
            if previous == "Busy" and status != "Busy" and current_customer and return_customer:
                _return_customer_to_queue(self.state, current_customer)
            if status == "Available":
                bonus = dict(self.state.get("bonusClockIns") or {})
                if not bonus.get(name):
                    bonus[name] = now_ms
                self.state["bonusClockIns"] = bonus
            if status != "Busy":
                tech["current"] = None
                tech["startTime"] = None
            elif not tech.get("current"):
                tech["startTime"] = now_ms
            tech["status"] = status
            self.state["techs"][name] = tech
            try_auto_assign(self.state)
        self.persist()
        return self.copy_for_client()

    def reassign_customer(self, from_tech: str, to_tech: str) -> dict[str, Any]:
        if from_tech == to_tech:
            raise ValueError("Source and destination must be different techs.")
        with self.lock:
            techs = self.state.get("techs") or {}
            source = techs.get(from_tech)
            dest = techs.get(to_tech)
            if not source or not dest:
                raise ValueError("Selected tech could not be found.")
            if source.get("status") != "Busy" or not source.get("current"):
                raise ValueError(f"{from_tech} does not have an active customer to reassign.")
            if dest.get("status") == "Busy":
                raise ValueError(f"{to_tech} is currently busy.")
            customer_name = source.get("current")
            now_ms = _now_ms()
            source["status"] = "Available"
            source["current"] = None
            source["startTime"] = None
            dest["status"] = "Busy"
            dest["current"] = customer_name
            dest["startTime"] = now_ms
            bonus = dict(self.state.get("bonusClockIns") or {})
            if not bonus.get(from_tech):
                bonus[from_tech] = now_ms
            self.state["bonusClockIns"] = bonus
            techs[from_tech] = source
            techs[to_tech] = dest
            self.state["techs"] = techs
        self.persist()
        return self.copy_for_client()

    def skip_turn(self, name: str) -> dict[str, Any]:
        with self.lock:
            techs = self.state.get("techs") or {}
            tech = techs.get(name)
            if not tech or tech.get("status") != "Available":
                raise ValueError(f"{name} must be available to skip a turn.")
            order = available_tech_order(self.state)
            if not order or order[0] != name:
                raise ValueError(f"{name} is not next in rotation right now.")
            bonus = dict(self.state.get("bonusClockIns") or {})
            latest = max([int(value or 0) for value in bonus.values()] + [0])
            bonus[name] = latest + 1
            self.state["bonusClockIns"] = bonus
            try_auto_assign(self.state)
        self.persist()
        return self.copy_for_client()

    def finish_service(self, tech_name: str, details: dict[str, Any]) -> tuple[dict[str, Any], str]:
        with self.lock:
            tech = (self.state.get("techs") or {}).get(tech_name)
            if not tech:
                raise ValueError("Tech was not found.")
            if tech.get("status") != "Busy":
                raise ValueError(f"{tech_name} is not currently serving a customer.")
            customer_name = str(tech.get("current") or "Customer")
            share = float(details.get("employeeShare") or 0)
            tech["earnings"] = round(float(tech.get("earnings") or 0) + share, 2)
            tech["status"] = "Available"
            tech["current"] = None
            tech["startTime"] = None
            bonus = dict(self.state.get("bonusClockIns") or {})
            if not bonus.get(tech_name):
                bonus[tech_name] = _now_ms()
            self.state["bonusClockIns"] = bonus
            self.state["techs"][tech_name] = tech
            try_auto_assign(self.state)
        self.persist()
        return self.copy_for_client(), customer_name

    def add_appointment(self, name: str, appointment_time: int, requested_tech: str = "", notes: str = "") -> dict[str, Any]:
        clean_name = str(name or "").strip()[:80]
        if not clean_name:
            raise ValueError("Customer name is required.")
        try:
            when = int(appointment_time)
        except (TypeError, ValueError) as error:
            raise ValueError("Appointment time is required.") from error
        requested = str(requested_tech or "").strip()
        with self.lock:
            if requested and requested not in (self.state.get("techs") or {}):
                raise ValueError("Requested tech was not found.")
            appt_id = int(self.state.get("nextAppointmentId") or 1)
            self.state.setdefault("appointments", []).append({
                "id": appt_id,
                "name": clean_name,
                "appointmentTime": when,
                "requestedTech": requested,
                "notes": str(notes or "").strip()[:200],
                "status": "booked",
            })
            self.state["nextAppointmentId"] = appt_id + 1
        self.persist()
        return self.copy_for_client()

    def arrive_appointment(self, appointment_id: int) -> dict[str, Any]:
        with self.lock:
            appointments = self.state.get("appointments") or []
            found = None
            for item in appointments:
                if int(item.get("id") or 0) == int(appointment_id):
                    found = item
                    break
            if not found:
                raise ValueError("Appointment was not found.")
            if found.get("status") != "booked":
                raise ValueError("Only booked appointments can be marked arrived.")
            found["status"] = "arrived"
            customer_id = int(self.state.get("nextCustomerId") or 1)
            self.state.setdefault("waitingQueue", []).append({
                "id": customer_id,
                "name": found.get("name") or "Customer",
                "arrival": _now_ms(),
                "requestedTech": found.get("requestedTech") or "",
                "appointmentTime": None,
            })
            self.state["nextCustomerId"] = customer_id + 1
            try_auto_assign(self.state)
        self.persist()
        return self.copy_for_client()

    def cancel_appointment(self, appointment_id: int) -> dict[str, Any]:
        with self.lock:
            appointments = self.state.get("appointments") or []
            found = None
            for item in appointments:
                if int(item.get("id") or 0) == int(appointment_id):
                    found = item
                    break
            if not found:
                raise ValueError("Appointment was not found.")
            found["status"] = "cancelled"
        self.persist()
        return self.copy_for_client()

    def end_of_day(self) -> dict[str, Any]:
        with self.lock:
            techs = self.state.get("techs") or {}
            snapshot = {
                "waitingQueue": deepcopy(self.state.get("waitingQueue") or []),
                "appointments": deepcopy(self.state.get("appointments") or []),
                "techs": deepcopy(techs),
                "closedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            for name, tech in techs.items():
                details = dict(tech or {})
                details["status"] = "Offline"
                details["current"] = None
                details["startTime"] = None
                details["earnings"] = 0
                techs[name] = details
            self.state["techs"] = techs
            self.state["waitingQueue"] = []
            remaining = []
            for item in self.state.get("appointments") or []:
                if item.get("status") == "booked" and int(item.get("appointmentTime") or 0) > _now_ms():
                    remaining.append(item)
            self.state["appointments"] = remaining
            self.state["bonusClockIns"] = {}
        self.persist()
        return snapshot

    def set_tech_login(self, tech_name: str, identifier: str, password: str, must_change: bool = True) -> None:
        with self.lock:
            credentials = dict(self.state.get("credentials") or {})
            normalized_id = str(identifier or "").strip().lower()
            for existing_name, cred in credentials.items():
                if existing_name == tech_name:
                    continue
                if str((cred or {}).get("identifier") or "").strip().lower() == normalized_id:
                    raise ValueError("This login ID is already in use by another tech.")
            credentials[tech_name] = {
                "identifier": str(identifier or "").strip(),
                "password": hash_secret(password),
                "mustChangePassword": must_change,
            }
            self.state["credentials"] = credentials
            _ensure_tech(self.state, tech_name)
            self._credentials_bootstrapped = True
        self.persist()

    def reset_tech_password(self, tech_name: str, password: str) -> None:
        with self.lock:
            credentials = dict(self.state.get("credentials") or {})
            current = dict(credentials.get(tech_name) or {})
            if not current.get("identifier"):
                current["identifier"] = str(tech_name).lower().replace(" ", "")
            current["password"] = hash_secret(password)
            current["mustChangePassword"] = True
            credentials[tech_name] = current
            self.state["credentials"] = credentials
            _ensure_tech(self.state, tech_name)
        self.persist()

    def delete_tech_login(self, tech_name: str) -> dict[str, Any] | None:
        with self.lock:
            credentials = dict(self.state.get("credentials") or {})
            removed = credentials.pop(tech_name, None)
            self.state["credentials"] = credentials
        self.persist()
        return removed

    def restore_tech_login(self, tech_name: str, credential: dict[str, Any] | None) -> None:
        if not credential:
            return
        with self.lock:
            credentials = dict(self.state.get("credentials") or {})
            restored = dict(credential)
            password = str(restored.get("password") or "")
            if password and not is_hashed_secret(password):
                restored["password"] = hash_secret(password)
            credentials[tech_name] = restored
            self.state["credentials"] = credentials
            _ensure_tech(self.state, tech_name)
            self._credentials_bootstrapped = True
        self.persist()

    def import_credentials(self, raw_credentials: dict) -> int:
        hashed = hash_credential_map(raw_credentials)
        with self.lock:
            merged = dict(self.state.get("credentials") or {})
            merged.update(hashed)
            self.state["credentials"] = merged
            for tech_name in hashed:
                _ensure_tech(self.state, tech_name)
            self._credentials_bootstrapped = bool(merged)
        self.persist()
        return len(hashed)

    def authenticate_tech(self, identifier: str, password: str) -> tuple[str | None, dict | None]:
        with self.lock:
            credentials = dict(self.state.get("credentials") or {})
            tech_name, cred, needs_rehash = find_tech_by_login(credentials, identifier, password)
            if tech_name and needs_rehash and cred is not None:
                cred["password"] = hash_secret(password)
                credentials[tech_name] = cred
                self.state["credentials"] = credentials
        if tech_name and needs_rehash:
            self.persist()
        return tech_name, cred

    def update_tech_password(self, tech_name: str, current_password: str, new_password: str) -> None:
        with self.lock:
            credentials = dict(self.state.get("credentials") or {})
            current = dict(credentials.get(tech_name) or {})
            matched, _needs_rehash = verify_secret(str(current.get("password") or ""), current_password)
            if not matched:
                raise ValueError("Current password is incorrect.")
            current["password"] = hash_secret(new_password)
            current["mustChangePassword"] = False
            credentials[tech_name] = current
            self.state["credentials"] = credentials
        self.persist()

    def update_tech_password_by_identifier(self, identifier: str, current_password: str, new_password: str) -> str:
        tech_name, cred = self.authenticate_tech(identifier, current_password)
        if not tech_name or cred is None:
            raise ValueError("Current credentials are incorrect.")
        self.update_tech_password(tech_name, current_password, new_password)
        return tech_name
