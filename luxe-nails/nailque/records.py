"""Manager activity log and completed-service history."""

from __future__ import annotations

import time
from typing import Any

from nailque.storage import read_json, write_json_atomic


def sanitize_activity_entry(payload: Any) -> dict[str, str] | None:
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


class JsonRecordStore:
    def __init__(self, path, keep_last: int):
        self.path = path
        self.keep_last = keep_last

    def read(self) -> list:
        records = read_json(self.path, [])
        return records if isinstance(records, list) else []

    def append(self, record: dict) -> None:
        records = self.read()
        records.append(record)
        records = records[-self.keep_last:]
        write_json_atomic(self.path, records)

    def replace(self, records: list) -> list:
        sanitized = records[-self.keep_last:]
        write_json_atomic(self.path, sanitized)
        return sanitized

    def clear(self) -> None:
        write_json_atomic(self.path, [])
