"""Password hashing, client IP checks, and request rate limiting."""

from __future__ import annotations

import hmac
import ipaddress
import threading
import time
from collections import defaultdict, deque

from werkzeug.security import check_password_hash, generate_password_hash

HASH_PREFIXES = ("pbkdf2:", "scrypt:", "argon2:")


def is_hashed_secret(value: str) -> bool:
    text = str(value or "")
    return text.startswith(HASH_PREFIXES)


def hash_secret(value: str) -> str:
    return generate_password_hash(str(value or ""), method="pbkdf2:sha256", salt_length=16)


def verify_secret(stored: str, provided: str) -> tuple[bool, bool]:
    """Return (matched, needs_rehash)."""
    stored_text = str(stored or "")
    provided_text = str(provided or "")
    if not stored_text or not provided_text:
        return False, False
    if is_hashed_secret(stored_text):
        return check_password_hash(stored_text, provided_text), False
    matched = hmac.compare_digest(stored_text, provided_text)
    return matched, matched


def is_private_or_loopback(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def request_client_ip(remote_addr: str, forwarded_for: str, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = (forwarded_for or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return remote_addr or ""


class RateLimiter:
    """In-memory sliding window limiter for login and PIN endpoints."""

    def __init__(self):
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True
