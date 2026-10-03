import os

from nailque.config import MANAGER_SETTINGS_FILE
from nailque.storage import read_json, write_json_atomic


def read_manager_settings():
    return read_json(MANAGER_SETTINGS_FILE, {})


def write_manager_settings(settings):
    write_json_atomic(MANAGER_SETTINGS_FILE, settings)


def normalize_manager_accounts(settings):
    managers = settings.get("managers")
    normalized = []
    if isinstance(managers, list):
        for item in managers:
            if not isinstance(item, dict):
                continue
            username = str(item.get("username") or "").strip().lower()
            full_name = str(item.get("fullName") or "").strip()
            pin = str(item.get("pin") or "").strip()
            if not username or not full_name or not pin:
                continue
            normalized.append({"username": username, "fullName": full_name, "pin": pin})
    return normalized


def get_manager_accounts():
    settings = read_manager_settings()
    managers = normalize_manager_accounts(settings)
    legacy_pin = str(settings.get("pin") or "").strip()
    default_name = str(os.getenv("MANAGER_FULL_NAME", "Admin")).strip() or "Admin"
    default_username = "admin"
    default_pin = str(os.getenv("MANAGER_PIN", "1234") or "1234").strip() or "1234"
    if not managers:
        managers = [{"username": default_username, "fullName": default_name, "pin": str(legacy_pin or default_pin)}]
        write_manager_settings({"managers": managers})
        return managers
    has_admin = any(str(manager.get("username") or "").strip().lower() == default_username for manager in managers)
    if not has_admin:
        managers.append({"username": default_username, "fullName": default_name, "pin": default_pin})
        write_manager_settings({"managers": managers})
    return managers


def find_manager(username: str, pin: str):
    normalized_username = str(username or "").strip().lower()
    normalized_pin = str(pin or "").strip()
    for manager in get_manager_accounts():
        if manager["username"] == normalized_username and manager["pin"] == normalized_pin:
            return manager
    return None


def get_manager_pin():
    managers = get_manager_accounts()
    if managers:
        return str(managers[0]["pin"])
    default_pin = os.getenv("MANAGER_PIN", "1234")
    return str(default_pin)


def set_manager_pin(username: str, new_pin: str):
    managers = get_manager_accounts()
    normalized_username = str(username or "").strip().lower()
    updated = False
    for manager in managers:
        if manager["username"] == normalized_username:
            manager["pin"] = str(new_pin)
            updated = True
            break
    if not updated:
        raise ValueError("Manager account not found.")
    write_manager_settings({"managers": managers})


def create_manager_account(full_name: str, username: str, pin: str):
    managers = get_manager_accounts()
    normalized_username = str(username or "").strip().lower()
    if any(manager["username"] == normalized_username for manager in managers):
        raise ValueError("Username already exists.")
    managers.append({
        "username": normalized_username,
        "fullName": str(full_name or "").strip(),
        "pin": str(pin or "").strip(),
    })
    write_manager_settings({"managers": managers})
