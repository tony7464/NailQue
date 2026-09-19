"""Salon service catalog and ticket totals."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_SERVICES_MENU = [
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

# Backwards-compatible alias used by older imports and tests.
SERVICES_MENU = DEFAULT_SERVICES_MENU

DEFAULT_COMMISSION_RATE = 0.6


def copy_default_services() -> list[dict[str, Any]]:
    return deepcopy(DEFAULT_SERVICES_MENU)


def normalize_services_menu(raw) -> list[dict[str, Any]]:
    menu = []
    if not isinstance(raw, list):
        return copy_default_services()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:80]
        if not name:
            continue
        try:
            price = round(float(item.get("price") or 0), 2)
        except (TypeError, ValueError):
            continue
        if price < 0:
            continue
        menu.append({"name": name, "price": price})
    return menu or copy_default_services()


def normalize_commission_rate(raw, default: float = DEFAULT_COMMISSION_RATE) -> float:
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return default
    if rate < 0.05 or rate > 1:
        return default
    return round(rate, 4)


def build_service_details(
    selected_service_indexes,
    custom_addons=None,
    services=None,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
) -> dict:
    menu = services if isinstance(services, list) and services else DEFAULT_SERVICES_MENU
    rate = normalize_commission_rate(commission_rate)
    total = 0.0
    selected_indexes = []
    selected_services = []
    normalized_addons = []
    for idx in selected_service_indexes:
        if not isinstance(idx, int):
            continue
        if idx < 0 or idx >= len(menu):
            continue
        selected_indexes.append(idx)
        service = menu[idx]
        selected_services.append(service["name"])
        total += float(service["price"])
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
        "employeeShare": round(total * rate, 2),
        "commissionRate": rate,
    }
