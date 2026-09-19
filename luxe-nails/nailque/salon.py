"""Salon-level settings: branding, menu, commission, and daily closings."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from nailque.catalog import (
    DEFAULT_COMMISSION_RATE,
    copy_default_services,
    normalize_commission_rate,
    normalize_services_menu,
)
from nailque.storage import read_json, write_json_atomic


def default_salon_settings() -> dict[str, Any]:
    return {
        "setupComplete": False,
        "salonName": "NailQue",
        "tagline": "NAIL SPA",
        "commissionRate": DEFAULT_COMMISSION_RATE,
        "services": copy_default_services(),
        "bonusHours": {"start": "08:00", "end": "09:30"},
        "idleLockMinutes": 5,
        "updatedAt": 0,
    }


def _hhmm_ok(value: str) -> bool:
    parts = str(value or "").split(":")
    if len(parts) != 2:
        return False
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59


class SalonStore:
    def __init__(self, settings_file):
        self.settings_file = settings_file
        self.settings = default_salon_settings()
        self.load()

    def load(self) -> None:
        saved = read_json(self.settings_file, default_salon_settings())
        if not isinstance(saved, dict):
            saved = default_salon_settings()
        merged = default_salon_settings()
        merged.update({key: saved[key] for key in merged if key in saved})
        merged["salonName"] = str(merged.get("salonName") or "NailQue").strip()[:80] or "NailQue"
        merged["tagline"] = str(merged.get("tagline") or "NAIL SPA").strip()[:40] or "NAIL SPA"
        merged["commissionRate"] = normalize_commission_rate(merged.get("commissionRate"))
        merged["services"] = normalize_services_menu(merged.get("services"))
        bonus = merged.get("bonusHours") if isinstance(merged.get("bonusHours"), dict) else {}
        start = str(bonus.get("start") or "08:00")
        end = str(bonus.get("end") or "09:30")
        if not _hhmm_ok(start):
            start = "08:00"
        if not _hhmm_ok(end):
            end = "09:30"
        merged["bonusHours"] = {"start": start, "end": end}
        try:
            idle = int(merged.get("idleLockMinutes") or 5)
        except (TypeError, ValueError):
            idle = 5
        merged["idleLockMinutes"] = min(60, max(1, idle))
        merged["setupComplete"] = bool(merged.get("setupComplete"))
        self.settings = merged

    def persist(self) -> None:
        self.settings["updatedAt"] = int(time.time())
        write_json_atomic(self.settings_file, self.settings)

    def public(self) -> dict[str, Any]:
        payload = deepcopy(self.settings)
        return payload

    def commission_rate(self) -> float:
        return normalize_commission_rate(self.settings.get("commissionRate"))

    def services(self) -> list[dict[str, Any]]:
        return deepcopy(self.settings.get("services") or copy_default_services())

    def salon_name(self) -> str:
        return str(self.settings.get("salonName") or "NailQue")

    def mark_setup_complete(self, salon_name: str, tagline: str = "NAIL SPA") -> None:
        self.settings["salonName"] = str(salon_name or "NailQue").strip()[:80] or "NailQue"
        self.settings["tagline"] = str(tagline or "NAIL SPA").strip()[:40] or "NAIL SPA"
        self.settings["setupComplete"] = True
        self.persist()

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "salonName" in payload:
            name = str(payload.get("salonName") or "").strip()[:80]
            if name:
                self.settings["salonName"] = name
        if "tagline" in payload:
            tagline = str(payload.get("tagline") or "").strip()[:40]
            if tagline:
                self.settings["tagline"] = tagline
        if "commissionRate" in payload:
            self.settings["commissionRate"] = normalize_commission_rate(
                payload.get("commissionRate"),
                default=self.commission_rate(),
            )
        if "services" in payload:
            self.settings["services"] = normalize_services_menu(payload.get("services"))
        if "bonusHours" in payload and isinstance(payload.get("bonusHours"), dict):
            start = str(payload["bonusHours"].get("start") or self.settings["bonusHours"]["start"])
            end = str(payload["bonusHours"].get("end") or self.settings["bonusHours"]["end"])
            if _hhmm_ok(start) and _hhmm_ok(end):
                self.settings["bonusHours"] = {"start": start, "end": end}
        if "idleLockMinutes" in payload:
            try:
                idle = int(payload.get("idleLockMinutes"))
                self.settings["idleLockMinutes"] = min(60, max(1, idle))
            except (TypeError, ValueError):
                pass
        self.persist()
        return self.public()
