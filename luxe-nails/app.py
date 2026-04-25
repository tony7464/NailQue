from flask import Flask, send_from_directory, request, jsonify
import os
import json
import uuid
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib import request as urlrequest
from urllib import parse as urlparse
from urllib.error import HTTPError, URLError
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INVITE_AUDIT_FILE = os.path.join(BASE_DIR, "invite_audit.json")
MANAGER_SETTINGS_FILE = os.path.join(BASE_DIR, "manager_settings.json")


def _read_audit_log():
    if not os.path.exists(INVITE_AUDIT_FILE):
        return []
    try:
        with open(INVITE_AUDIT_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return []


def _write_audit_log(entries):
    with open(INVITE_AUDIT_FILE, "w", encoding="utf-8") as file:
        json.dump(entries, file, indent=2)


def _append_audit(entry):
    entries = _read_audit_log()
    entries.append(entry)
    _write_audit_log(entries)


def _read_manager_settings():
    if not os.path.exists(MANAGER_SETTINGS_FILE):
        return {}
    try:
        with open(MANAGER_SETTINGS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_manager_settings(settings):
    with open(MANAGER_SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file, indent=2)


def _get_manager_pin():
    settings = _read_manager_settings()
    if settings.get("pin"):
        return str(settings.get("pin"))
    default_pin = os.getenv("MANAGER_PIN", "1234")
    _write_manager_settings({"pin": default_pin})
    return str(default_pin)


def _set_manager_pin(new_pin):
    _write_manager_settings({"pin": str(new_pin)})


def _get_invite(invite_id):
    entries = _read_audit_log()
    for entry in entries:
        if entry.get("id") == invite_id:
            return entry
    return None


def _update_invite(invite_id, updater):
    entries = _read_audit_log()
    updated = None
    for idx, entry in enumerate(entries):
        if entry.get("id") == invite_id:
            updated_entry = dict(entry)
            updater(updated_entry)
            entries[idx] = updated_entry
            updated = updated_entry
            break
    if updated is not None:
        _write_audit_log(entries)
    return updated


def _is_valid_email(value):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value))


def _normalize_phone(value):
    digits = re.sub(r"[^\d+]", "", value)
    if digits.startswith("00"):
        digits = f"+{digits[2:]}"
    if not digits.startswith("+") and len(digits) == 10:
        digits = f"+1{digits}"
    return digits


def _build_invite_link(token):
    base = os.getenv("APP_BASE_URL", "http://localhost:5001")
    return f"{base}/employee?invite={token}"


def _send_email_invite(target, tech_name, invite_link):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("EMAIL_FROM")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not host or not from_email:
        raise ValueError("Email provider not configured. Set SMTP_HOST and EMAIL_FROM.")

    msg = EmailMessage()
    msg["Subject"] = "M. VINCE Nail Spa Invite"
    msg["From"] = from_email
    msg["To"] = target
    msg.set_content(
        f"Hi {tech_name},\n\n"
        f"You have been invited to set up your employee account.\n"
        f"Open this link to continue: {invite_link}\n\n"
        "If you did not expect this invitation, ignore this message."
    )

    with smtplib.SMTP(host, port, timeout=20) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg)


def _send_sms_invite(target, tech_name, invite_link):
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    if not sid or not token or not from_number:
        raise ValueError("SMS provider not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.")

    body = (
        f"Hi {tech_name}, you are invited to set up your M. VINCE Nail Spa employee account. "
        f"Complete setup: {invite_link}"
    )
    payload = urlparse.urlencode({"To": target, "From": from_number, "Body": body}).encode("utf-8")
    req = urlrequest.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=payload,
        method="POST"
    )
    credentials = f"{sid}:{token}".encode("utf-8")
    encoded = __import__("base64").b64encode(credentials).decode("ascii")
    req.add_header("Authorization", f"Basic {encoded}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            if response.status not in (200, 201):
                raise ValueError(f"SMS provider returned status {response.status}")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="ignore")
        raise ValueError(f"SMS delivery failed: {body or error.reason}") from error
    except URLError as error:
        raise ValueError(f"SMS delivery failed: {error.reason}") from error


@app.route('/api/invites', methods=['POST'])
def create_invite():
    payload = request.get_json(silent=True) or {}
    tech_name = (payload.get("techName") or "").strip()
    contact = (payload.get("contact") or "").strip()
    channel = (payload.get("channel") or "").strip().lower()

    if not tech_name or not contact or channel not in {"email", "sms"}:
        return jsonify({"error": "techName, contact, and channel(email|sms) are required."}), 400

    normalized_contact = contact
    if channel == "email":
        if not _is_valid_email(contact):
            return jsonify({"error": "Invalid email address."}), 400
        normalized_contact = contact.lower()
    else:
        normalized_contact = _normalize_phone(contact)
        if not normalized_contact.startswith("+") or len(re.sub(r"[^\d]", "", normalized_contact)) < 10:
            return jsonify({"error": "Invalid phone number."}), 400

    invite_token = str(uuid.uuid4())
    invite_link = _build_invite_link(invite_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)
    audit_entry = {
        "id": invite_token,
        "techName": tech_name,
        "contact": normalized_contact,
        "channel": channel,
        "inviteLink": invite_link,
        "createdAt": now.isoformat(),
        "expiresAt": expires_at.isoformat(),
        "status": "pending"
    }

    try:
        if channel == "email":
            _send_email_invite(normalized_contact, tech_name, invite_link)
        else:
            _send_sms_invite(normalized_contact, tech_name, invite_link)
        audit_entry["status"] = "sent"
        _append_audit(audit_entry)
        return jsonify({
            "ok": True,
            "inviteId": invite_token,
            "techName": tech_name,
            "identifier": normalized_contact,
            "channel": channel
        })
    except ValueError as error:
        audit_entry["status"] = "failed"
        audit_entry["error"] = str(error)
        _append_audit(audit_entry)
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        audit_entry["status"] = "failed"
        audit_entry["error"] = str(error)
        _append_audit(audit_entry)
        return jsonify({"error": "Unexpected invite failure."}), 500


@app.route('/api/invites/test', methods=['POST'])
def test_invite_provider():
    channel = ((request.get_json(silent=True) or {}).get("channel") or "email").lower()
    try:
        if channel == "sms":
            if not os.getenv("TWILIO_ACCOUNT_SID") or not os.getenv("TWILIO_AUTH_TOKEN") or not os.getenv("TWILIO_FROM_NUMBER"):
                raise ValueError("Twilio configuration missing.")
        else:
            if not os.getenv("SMTP_HOST") or not os.getenv("EMAIL_FROM"):
                raise ValueError("SMTP configuration missing.")
        return jsonify({"ok": True, "channel": channel})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.route('/api/invites/<invite_id>', methods=['GET'])
def get_invite(invite_id):
    invite = _get_invite(invite_id)
    if not invite:
        return jsonify({"error": "Invite not found."}), 404
    if invite.get("status") == "accepted":
        return jsonify({"error": "Invite already used."}), 400
    expires_at = invite.get("expiresAt")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
        return jsonify({"error": "Invite expired."}), 400
    return jsonify({
        "ok": True,
        "techName": invite.get("techName"),
        "identifier": invite.get("contact"),
        "channel": invite.get("channel")
    })


@app.route('/api/invites/accept', methods=['POST'])
def accept_invite():
    payload = request.get_json(silent=True) or {}
    invite_id = str(payload.get("inviteId") or "")
    password = str(payload.get("password") or "")
    if not invite_id or len(password) < 4:
        return jsonify({"error": "inviteId and password(min 4 chars) are required."}), 400

    invite = _get_invite(invite_id)
    if not invite:
        return jsonify({"error": "Invite not found."}), 404
    if invite.get("status") == "accepted":
        return jsonify({"error": "Invite already used."}), 400
    expires_at = invite.get("expiresAt")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
        return jsonify({"error": "Invite expired."}), 400

    updated = _update_invite(invite_id, lambda entry: entry.update({
        "status": "accepted",
        "acceptedAt": datetime.now(timezone.utc).isoformat()
    }))
    return jsonify({
        "ok": True,
        "techName": updated.get("techName"),
        "identifier": updated.get("contact"),
        "password": password
    })


@app.route('/api/manager/verify-pin', methods=['POST'])
def verify_manager_pin():
    entered = str((request.get_json(silent=True) or {}).get("pin") or "")
    manager_pin = _get_manager_pin()
    return jsonify({"ok": entered == manager_pin})


@app.route('/api/manager/set-pin', methods=['POST'])
def set_manager_pin():
    payload = request.get_json(silent=True) or {}
    current_pin = str(payload.get("currentPin") or "")
    new_pin = str(payload.get("newPin") or "")

    if current_pin != _get_manager_pin():
        return jsonify({"error": "Current PIN is incorrect."}), 400
    if not new_pin.isdigit() or len(new_pin) < 4:
        return jsonify({"error": "New PIN must be at least 4 digits."}), 400

    _set_manager_pin(new_pin)
    return jsonify({"ok": True})

# Main Queue (TV/monitor) - accessed at http://YOUR-IP:5001/
@app.route('/')
def main_queue():
    return send_from_directory('.', 'luxe-nails-queue.html')

# Employee Portal (phones) - accessed at http://YOUR-IP:5001/employee
@app.route('/employee')
def employee_portal():
    return send_from_directory('.', 'luxe-nails-employee.html')

# Allow serving any other files if needed (images, etc.)
@app.route('/<path:path>')
def serve_file(path):
    return send_from_directory('.', path)

if __name__ == '__main__':
    print("\n🚀 Luxe Nails Website Started on PORT 5001")
    print("   Main Queue (TV)     → http://YOUR-IP:5001")
    print("   Employee Portal     → http://YOUR-IP:5001/employee")
    print("   Press Ctrl+C to stop\n")
    app.run(host='0.0.0.0', port=5001, debug=False)