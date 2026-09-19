"""Manager account storage with hashed PINs."""

from __future__ import annotations

from typing import Any

from nailque.security import hash_secret, is_hashed_secret, verify_secret
from nailque.storage import read_json, write_json_atomic


def public_manager(manager: dict[str, Any]) -> dict[str, str]:
    return {
        "username": str(manager.get("username") or ""),
        "fullName": str(manager.get("fullName") or ""),
    }


class ManagerStore:
    def __init__(self, settings_file, default_name: str, default_username: str, default_pin: str):
        self.settings_file = settings_file
        self.default_name = default_name
        self.default_username = default_username
        self.default_pin = default_pin

    def _read(self) -> dict[str, Any]:
        data = read_json(self.settings_file, {})
        return data if isinstance(data, dict) else {}

    def _write(self, managers: list[dict[str, str]]) -> None:
        write_json_atomic(self.settings_file, {"managers": managers})

    def _normalize(self, settings: dict[str, Any]) -> list[dict[str, str]]:
        managers = settings.get("managers")
        normalized = []
        dirty = False
        if isinstance(managers, list):
            for item in managers:
                if not isinstance(item, dict):
                    continue
                username = str(item.get("username") or "").strip().lower()
                full_name = str(item.get("fullName") or "").strip()
                pin = str(item.get("pin") or "").strip()
                if not username or not full_name or not pin:
                    continue
                if not is_hashed_secret(pin):
                    pin = hash_secret(pin)
                    dirty = True
                normalized.append({"username": username, "fullName": full_name, "pin": pin})
        if normalized:
            if dirty:
                self._write(normalized)
            return normalized
        legacy_pin = str(settings.get("pin") or "").strip() or self.default_pin
        seeded = [{
            "username": self.default_username,
            "fullName": self.default_name,
            "pin": hash_secret(legacy_pin),
        }]
        self._write(seeded)
        return seeded

    def list_accounts(self) -> list[dict[str, str]]:
        return self._normalize(self._read())

    def public_accounts(self) -> list[dict[str, str]]:
        return [public_manager(manager) for manager in self.list_accounts()]

    def authenticate(self, username: str, pin: str) -> dict[str, str] | None:
        wanted = str(username or "").strip().lower()
        provided = str(pin or "").strip()
        if not wanted or not provided:
            return None
        managers = self.list_accounts()
        matched = None
        dirty = False
        for manager in managers:
            if manager["username"] != wanted:
                continue
            ok, needs_rehash = verify_secret(manager["pin"], provided)
            if not ok:
                return None
            if needs_rehash:
                manager["pin"] = hash_secret(provided)
                dirty = True
            matched = manager
            break
        if dirty:
            self._write(managers)
        return dict(matched) if matched else None

    def set_pin(self, username: str, current_pin: str, new_pin: str) -> None:
        manager = self.authenticate(username, current_pin)
        if not manager:
            raise ValueError("Current PIN is incorrect.")
        managers = self.list_accounts()
        updated = False
        for item in managers:
            if item["username"] == manager["username"]:
                item["pin"] = hash_secret(new_pin)
                updated = True
                break
        if not updated:
            raise ValueError("Manager account not found.")
        self._write(managers)

    def create_account(self, full_name: str, username: str, pin: str) -> None:
        managers = self.list_accounts()
        normalized_username = str(username or "").strip().lower()
        if any(item["username"] == normalized_username for item in managers):
            raise ValueError("Username already exists.")
        managers.append({
            "username": normalized_username,
            "fullName": str(full_name or "").strip(),
            "pin": hash_secret(str(pin or "").strip()),
        })
        self._write(managers)
