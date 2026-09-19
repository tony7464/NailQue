import json


def test_health_does_not_leak_runtime_path(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["service"] == "nailque"
    assert "runtime_dir" not in payload


def test_shared_state_omits_credentials(client):
    response = client.get("/api/shared/state")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "credentials" not in payload["state"]
    dumped = json.dumps(payload)
    assert "password" not in dumped


def test_manager_endpoints_require_auth(client):
    assert client.get("/api/manager/accounts").status_code == 401
    assert client.post("/api/manager/create-account", json={"fullName": "Pat Lee", "username": "pat", "pin": "2222"}).status_code == 401
    assert client.get("/api/update/status").status_code == 401
    assert client.post("/api/update/install").status_code == 401
    assert client.get("/api/services/history").status_code == 401


def test_python_source_is_not_served(client):
    response = client.get("/app.py")
    assert response.status_code in {404, 200}
    body = response.get_data(as_text=True)
    assert "from flask import" not in body
    assert "MANAGER_PIN" not in body


def test_manager_pin_login_and_account_create(client):
    denied = client.post("/api/manager/verify-pin", json={"username": "admin", "pin": "0000"})
    assert denied.get_json()["ok"] is False

    login = client.post("/api/manager/verify-pin", json={"username": "admin", "pin": "1234"})
    payload = login.get_json()
    assert payload["ok"] is True
    token = payload["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/manager/create-account",
        json={"fullName": "Pat Lee", "username": "pat", "pin": "5678"},
        headers=headers,
    )
    assert created.status_code == 200
    accounts = client.get("/api/manager/accounts", headers=headers).get_json()
    usernames = {item["username"] for item in accounts["managers"]}
    assert "pat" in usernames
    assert all("pin" not in item for item in accounts["managers"])


def test_queue_pages_load(client):
    assert client.get("/").status_code == 200
    assert client.get("/employee").status_code == 200
    assert client.get("/mobile").status_code == 200
    assert client.get("/static/js/http.js").status_code == 200
    assert client.get("/static/css/queue.css").status_code == 200
