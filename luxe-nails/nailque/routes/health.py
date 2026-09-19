"""Health and LAN network info endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from nailque.factory import get_ctx
from nailque.http import require_lan
from nailque.network import detect_lan_ip, qr_png_data_url

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health", methods=["GET"])
def health():
    ctx = get_ctx()
    return jsonify({
        "ok": True,
        "service": "nailque",
        "version": ctx.settings.app_version,
        "setupComplete": ctx.managers.is_setup_complete(),
        "https": ctx.settings.https_enabled,
    })


@health_bp.route("/api/network-info", methods=["GET"])
@require_lan
def network_info():
    ctx = get_ctx()
    lan_ip = detect_lan_ip()
    mobile_url = f"{ctx.settings.http_scheme}://{lan_ip}:{ctx.settings.port}/mobile"
    return jsonify({
        "ok": True,
        "lan_ip": lan_ip,
        "mobile_url": mobile_url,
        "mobile_qr_data_url": qr_png_data_url(mobile_url),
    })
