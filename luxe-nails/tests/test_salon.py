def test_setup_page_is_served_before_wizard(fresh_app):
    client = fresh_app.test_client()
    response = client.get("/setup")
    assert response.status_code == 200
    assert b"Set up this salon" in response.data


def test_setup_wizard_creates_manager(fresh_app):
    client = fresh_app.test_client()
    status = client.get("/api/setup/status").get_json()
    assert status["setupComplete"] is False
    assert client.get("/").status_code == 302

    created = client.post("/api/setup", json={
        "salonName": "Luxe Nails",
        "tagline": "NAIL SPA",
        "fullName": "Maria Lopez",
        "username": "mlopez",
        "pin": "2468",
    })
    payload = created.get_json()
    assert created.status_code == 200
    assert payload["ok"] is True
    assert payload["manager"]["username"] == "mlopez"
    assert client.get("/").status_code == 200
    assert client.get("/setup").status_code == 302

    again = client.post("/api/setup", json={
        "salonName": "Nope",
        "fullName": "Other Person",
        "username": "other",
        "pin": "1357",
    })
    assert again.status_code == 409


def test_default_pin_forces_change_flag(fresh_app):
    client = fresh_app.test_client()
    created = client.post("/api/setup", json={
        "salonName": "Test Salon",
        "fullName": "Admin User",
        "username": "admin",
        "pin": "1234",
    })
    assert created.get_json()["mustChangePin"] is True
    login = client.post("/api/manager/verify-pin", json={"username": "admin", "pin": "1234"})
    assert login.get_json()["mustChangePin"] is True


def test_salon_settings_update_changes_commission_and_menu(client):
    login = client.post("/api/manager/verify-pin", json={"username": "admin", "pin": "1234"})
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}
    updated = client.put("/api/salon/settings", json={
        "salonName": "New Name",
        "commissionRate": 0.5,
        "services": [{"name": "Gel", "price": 20}],
        "idleLockMinutes": 8,
    }, headers=headers)
    payload = updated.get_json()
    assert payload["ok"] is True
    assert payload["settings"]["salonName"] == "New Name"
    assert payload["settings"]["commissionRate"] == 0.5
    assert payload["settings"]["services"] == [{"name": "Gel", "price": 20.0}]
    assert payload["settings"]["idleLockMinutes"] == 8

    ticket = client.post("/api/queue/action", json={
        "action": "upsert_tech",
        "name": "Mia T",
    })
    assert ticket.status_code == 200
    client.post("/api/queue/action", json={"action": "set_status", "name": "Mia T", "status": "Available"})
    client.post("/api/queue/action", json={"action": "add_customer", "name": "Jordan"})
    finished = client.post("/api/queue/action", json={
        "action": "finish",
        "name": "Mia T",
        "selectedServiceIndexes": [0],
    })
    receipt = finished.get_json()["receipt"]
    assert receipt["total"] == 20.0
    assert receipt["employeeShare"] == 10.0
    fetched = client.get(f"/api/receipts/{receipt['receiptId']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["receipt"]["receiptId"] == receipt["receiptId"]
