"""Shared front-desk queue state and automatic assignment."""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any

from nailque.security import hash_secret, is_hashed_secret, verify_secret
from nailque.storage import read_json, write_json_atomic


def empty_shared_state() -> dict[str, Any]:
    return {
        "techs": {},
        "waitingQueue": [],
        "nextCustomerId": 1,
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
        "nextCustomerId": int(state.get("nextCustomerId") or 1),
        "bonusClockIns": deepcopy(state.get("bonusClockIns") or {}),
        "updatedAt": int(state.get("updatedAt") or 0),
        "credentialsConfigured": bool(state.get("credentials")),
    }
    if include_credential_meta:
        payload["credentialMeta"] = public_credential_meta(state.get("credentials") or {})
    return payload


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
    now_ms = int(time.time() * 1000)

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
        with self.lock:
            if isinstance(payload.get("techs"), dict):
                self.state["techs"] = payload.get("techs")
            if isinstance(payload.get("waitingQueue"), list):
                self.state["waitingQueue"] = payload.get("waitingQueue")
            if isinstance(payload.get("bonusClockIns"), dict):
                self.state["bonusClockIns"] = payload.get("bonusClockIns")
            if isinstance(payload.get("nextCustomerId"), int):
                self.state["nextCustomerId"] = payload.get("nextCustomerId")
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
            self._credentials_bootstrapped = True
        self.persist()

    def import_credentials(self, raw_credentials: dict) -> int:
        hashed = hash_credential_map(raw_credentials)
        with self.lock:
            merged = dict(self.state.get("credentials") or {})
            merged.update(hashed)
            self.state["credentials"] = merged
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
