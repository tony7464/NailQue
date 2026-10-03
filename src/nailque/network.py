import base64
import io
import ipaddress
import socket

import qrcode
from flask import jsonify, request


def detect_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def is_private_or_loopback(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def is_same_lan_client(ip_text: str) -> bool:
    # Restrict to private/loopback ranges; this keeps access local-network only
    # while avoiding false negatives across different private subnet masks.
    return is_private_or_loopback(ip_text)


def request_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.remote_addr or ""


def mobile_requires_lan():
    client_ip = request_client_ip()
    if not is_same_lan_client(client_ip):
        return jsonify({"error": "Mobile access is only allowed from the same local network."}), 403
    return None


def qr_png_data_url(text: str) -> str:
    qr = qrcode.QRCode(border=2, box_size=6)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
