"""Manager account storage with hashed PINs."""

from __future__ import annotations

from typing import Any

from nailque.security import hash_secret, is_hashed_secret, verify_secret
from nailque.storage import read_json, write_json_atomic


def public_manager(manager: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(manager.get("username") or ""),
        "fullName": str(manager.get("fullName") or ""),
        "mustChangePin": bool(manager.get("mustChangePin")),
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

    def _write(self, managers: list[dict[str, Any]], setup_complete: bool) -> None:
        write_json_atomic(
            self.settings_file,
            {"managers": managers, "setupComplete": setup_complete},
        )

    def _normalize_manager(self, item: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
        username = str(item.get("username") or "").strip().lower()
        full_name = str(item.get("fullName") or "").strip()
        pin = str(item.get("pin") or "").strip()
        if not username or not full_name or not pin:
            return None, False
        dirty = False
        if not is_hashed_secret(pin):
            pin = hash_secret(pin)
            dirty = True
        return {
            "username": username,
            "fullName": full_name,
            "pin": pin,
            "mustChangePin": bool(item.get("mustChangePin")),
        }, dirty

    def _load(self) -> tuple[list[dict[str, Any]], bool]:
        settings = self._read()
        managers = settings.get("managers")
        normalized = []
        dirty = False
        if isinstance(managers, list):
            for item in managers:
                if not isinstance(item, dict):
                    continue
                manager, item_dirty = self._normalize_manager(item)
                if manager is None:
                    continue
                dirty = dirty or item_dirty
                normalized.append(manager)
        setup_complete = bool(settings.get("setupComplete"))
        if normalized and not setup_complete:
            # Existing salon files from before the setup wizard.
            setup_complete = True
            for manager in normalized:
                manager["mustChangePin"] = True
            dirty = True
        if dirty:
            self._write(normalized, setup_complete)
        return normalized, setup_complete

    def is_setup_complete(self) -> bool:
        managers, setup_complete = self._load()
        return bool(setup_complete and managers)

    def list_accounts(self) -> list[dict[str, Any]]:
        managers, _setup_complete = self._load()
        return managers

    def public_accounts(self) -> list[dict[str, Any]]:
        return [public_manager(manager) for manager in self.list_accounts()]

    def authenticate(self, username: str, pin: str) -> dict[str, Any] | None:
        wanted = str(username or "").strip().lower()
        provided = str(pin or "").strip()
        if not wanted or not provided:
            return None
        managers, setup_complete = self._load()
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
            self._write(managers, setup_complete)
        return dict(matched) if matched else None

    def set_pin(self, username: str, current_pin: str, new_pin: str) -> None:
        manager = self.authenticate(username, current_pin)
        if not manager:
            raise ValueError("Current PIN is incorrect.")
        if str(new_pin).strip() == str(current_pin).strip():
            raise ValueError("New PIN must be different from the current PIN.")
        managers, setup_complete = self._load()
        updated = False
        for item in managers:
            if item["username"] == manager["username"]:
                item["pin"] = hash_secret(new_pin)
                item["mustChangePin"] = False
                updated = True
                break
        if not updated:
            raise ValueError("Manager account not found.")
        self._write(managers, setup_complete)

    def create_account(self, full_name: str, username: str, pin: str, must_change_pin: bool = False) -> None:
        managers, setup_complete = self._load()
        normalized_username = str(username or "").strip().lower()
        if any(item["username"] == normalized_username for item in managers):
            raise ValueError("Username already exists.")
        managers.append({
            "username": normalized_username,
            "fullName": str(full_name or "").strip(),
            "pin": hash_secret(str(pin or "").strip()),
            "mustChangePin": bool(must_change_pin),
        })
        self._write(managers, setup_complete)

    def complete_setup(self, full_name: str, username: str, pin: str) -> dict[str, Any]:
        managers, setup_complete = self._load()
        if setup_complete and managers:
            raise ValueError("Salon setup is already complete.")
        normalized_username = str(username or "").strip().lower()
        full_name = str(full_name or "").strip()
        pin = str(pin or "").strip()
        if not full_name or " " not in full_name:
            raise ValueError("Full name must include first and last name.")
        if not normalized_username or not normalized_username.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must use letters, numbers, dashes, or underscores.")
        if not pin.isdigit() or not (4 <= len(pin) <= 12):
            raise ValueError("PIN must be 4 to 12 digits.")
        seeded = [{
            "username": normalized_username,
            "fullName": full_name,
            "pin": hash_secret(pin),
            "mustChangePin": pin == "1234",
        }]
        self._write(seeded, True)
        return public_manager(seeded[0])
