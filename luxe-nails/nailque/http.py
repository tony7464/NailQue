"""Request helpers shared by API blueprints."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, request

from nailque.factory import get_ctx
from nailque.security import is_private_or_loopback, request_client_ip
from nailque.sessions import bearer_token_from_header


def client_ip() -> str:
    ctx = get_ctx()
    return request_client_ip(
        request.remote_addr or "",
        request.headers.get("X-Forwarded-For", ""),
        ctx.settings.trust_proxy,
    )


def require_lan(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_private_or_loopback(client_ip()):
            return jsonify({"error": "This resource is only available on the local network."}), 403
        return fn(*args, **kwargs)

    return wrapper


def _session_from_store(store) -> dict | None:
    token = bearer_token_from_header(request.headers.get("Authorization", ""))
    return store.resolve(token, client_ip())


def require_manager(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        ctx = get_ctx()
        session = _session_from_store(ctx.manager_sessions)
        if not session:
            return jsonify({"error": "Unauthorized."}), 401
        request.manager_session = session  # noqa: SLF001
        return fn(*args, **kwargs)

    return wrapper


def require_mobile(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        ctx = get_ctx()
        session = _session_from_store(ctx.mobile_sessions)
        if not session:
            return jsonify({"error": "Unauthorized."}), 401
        request.mobile_session = session  # noqa: SLF001
        return fn(*args, **kwargs)

    return wrapper


def require_employee(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        ctx = get_ctx()
        session = _session_from_store(ctx.employee_sessions)
        if not session:
            return jsonify({"error": "Unauthorized."}), 401
        request.employee_session = session  # noqa: SLF001
        return fn(*args, **kwargs)

    return wrapper


def rate_limited(kind: str, limit: int = 8, window_seconds: int = 300):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            ctx = get_ctx()
            key = f"{kind}:{client_ip()}"
            if not ctx.rate_limiter.allow(key, limit, window_seconds):
                return jsonify({"error": "Too many attempts. Try again later."}), 429
            return fn(*args, **kwargs)

        return wrapper

    return decorator
