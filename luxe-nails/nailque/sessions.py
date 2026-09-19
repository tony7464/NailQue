"""Bearer token sessions for managers, employees, and mobile techs."""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any


class TokenStore:
    def __init__(self, ttl_seconds: int, bind_ip: bool = True):
        self.ttl_seconds = ttl_seconds
        self.bind_ip = bind_ip
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}

    def _cleanup_unlocked(self) -> None:
        now = int(time.time())
        expired = [token for token, item in self._items.items() if int(item.get("expiresAt") or 0) <= now]
        for token in expired:
            self._items.pop(token, None)

    def create(self, payload: dict[str, Any], client_ip: str = "") -> str:
        token = secrets.token_urlsafe(32)
        record = dict(payload)
        record["ip"] = str(client_ip or "")
        record["expiresAt"] = int(time.time()) + self.ttl_seconds
        with self._lock:
            self._cleanup_unlocked()
            self._items[token] = record
        return token

    def resolve(self, token: str | None, client_ip: str = "") -> dict[str, Any] | None:
        if not token:
            return None
        now = int(time.time())
        with self._lock:
            self._cleanup_unlocked()
            session = self._items.get(token)
            if not session:
                return None
            if int(session.get("expiresAt") or 0) <= now:
                self._items.pop(token, None)
                return None
            if self.bind_ip and session.get("ip") and session.get("ip") != client_ip:
                return None
            return dict(session)

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._items.pop(token, None)

    def active_payloads(self) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._lock:
            self._cleanup_unlocked()
            return [dict(item) for item in self._items.values() if int(item.get("expiresAt") or 0) > now]


def bearer_token_from_header(authorization: str) -> str:
    auth = str(authorization or "")
    if not auth.startswith("Bearer "):
        return ""
    return auth.replace("Bearer ", "", 1).strip()
