# Provider Setup (Email + SMS)

This project sends manager invites from backend endpoint `POST /api/invites`.

## 1) Install dependencies

From `luxe-nails`:

```bash
pip install -r requirements.txt
```

## 2) Create `.env`

Copy `.env.example` to `.env` and fill real values.

```bash
cp .env.example .env
```

## 3) Configure email provider (SMTP)

Required:

- `EMAIL_FROM`
- `SMTP_HOST`

Recommended:

- `SMTP_PORT=587`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS=true`

Example (SendGrid SMTP):

- `SMTP_HOST=smtp.sendgrid.net`
- `SMTP_PORT=587`
- `SMTP_USERNAME=apikey`
- `SMTP_PASSWORD=<your_sendgrid_api_key>`
- `EMAIL_FROM=<verified_sender@yourdomain.com>`

## 4) Configure SMS provider (Twilio)

Required:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER` (Twilio number in E.164 format, e.g. `+15551234567`)

## 5) Set manager PIN and base URL

- `MANAGER_PIN=1234` (change to a secure PIN for production)
- `APP_BASE_URL=http://localhost:5001` (or your LAN/public URL)

## 6) Validate provider config

Start app:

```bash
python app.py
```

Run config checks:

```bash
curl -X POST http://localhost:5001/api/invites/test -H "Content-Type: application/json" -d '{"channel":"email"}'
curl -X POST http://localhost:5001/api/invites/test -H "Content-Type: application/json" -d '{"channel":"sms"}'
```

You should get:

```json
{"ok": true, "channel": "email"}
```

or

```json
{"ok": true, "channel": "sms"}
```

## 7) Send a real invite test

Email:

```bash
curl -X POST http://localhost:5001/api/invites \
  -H "Content-Type: application/json" \
  -d '{"techName":"Mia","contact":"mia@example.com","channel":"email"}'
```

SMS:

```bash
curl -X POST http://localhost:5001/api/invites \
  -H "Content-Type: application/json" \
  -d '{"techName":"Mia","contact":"+15551234567","channel":"sms"}'
```

Invite audit events are written to `invite_audit.json`.
