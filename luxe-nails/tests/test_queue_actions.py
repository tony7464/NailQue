def _manager_headers(client):
    login = client.post("/api/manager/verify-pin", json={"username": "admin", "pin": "1234"})
    token = login.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_desk_sync_does_not_overwrite_server_queue(client):
    client.post("/api/queue/action", json={"action": "upsert_tech", "name": "Mia T"})
    client.post("/api/queue/action", json={"action": "set_status", "name": "Mia T", "status": "Available"})
    added = client.post("/api/queue/action", json={"action": "add_customer", "name": "Jordan"})
    assert added.status_code == 200
    clobber = client.post("/api/shared/sync", json={
        "techs": {"Stale": {"status": "Offline", "current": None, "startTime": None, "earnings": 0}},
        "waitingQueue": [],
        "nextCustomerId": 1,
        "bonusClockIns": {},
    })
    assert clobber.status_code == 200
    state = client.get("/api/shared/state").get_json()["state"]
    assert "Mia T" in state["techs"]
    names = [item["name"] for item in state["waitingQueue"]]
    # Jordan may already be auto-assigned to Mia T.
    assigned = state["techs"]["Mia T"].get("current") == "Jordan"
    assert assigned or "Jordan" in names


def test_add_customer_auto_assigns_available_tech(client):
    client.post("/api/queue/action", json={"action": "upsert_tech", "name": "Mia T"})
    client.post("/api/queue/action", json={"action": "set_status", "name": "Mia T", "status": "Available"})
    response = client.post("/api/queue/action", json={"action": "add_customer", "name": "Jordan"})
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["state"]["techs"]["Mia T"]["status"] == "Busy"
    assert payload["state"]["techs"]["Mia T"]["current"] == "Jordan"
    assert payload["state"]["waitingQueue"] == []


def test_mobile_finish_is_not_undone_by_stale_desk_sync(client):
    client.post("/api/queue/action", json={"action": "upsert_tech", "name": "Mia T"})
    client.post("/api/queue/action", json={"action": "set_status", "name": "Mia T", "status": "Available"})
    client.post("/api/queue/action", json={"action": "add_customer", "name": "Jordan"})
    finished = client.post("/api/queue/action", json={
        "action": "finish",
        "name": "Mia T",
        "selectedServiceIndexes": [0],
        "customAddons": [],
    })
    assert finished.status_code == 200
    assert finished.get_json()["receipt"]["customer"] == "Jordan"
    client.post("/api/shared/sync", json={
        "techs": {"Mia T": {"status": "Busy", "current": "Jordan", "startTime": 1, "earnings": 0}},
        "waitingQueue": [],
    })
    state = client.get("/api/shared/state").get_json()["state"]
    assert state["techs"]["Mia T"]["status"] == "Available"
    assert not state["techs"]["Mia T"].get("current")


def test_appointment_book_arrive_moves_to_queue(client):
    client.post("/api/queue/action", json={"action": "upsert_tech", "name": "Mia T"})
    when = 1_900_000_000_000
    booked = client.post("/api/queue/action", json={
        "action": "add_appointment",
        "name": "Sam",
        "appointmentTime": when,
        "requestedTech": "Mia T",
    })
    assert booked.status_code == 200
    appt = booked.get_json()["state"]["appointments"][0]
    arrived = client.post("/api/queue/action", json={"action": "arrive_appointment", "id": appt["id"]})
    state = arrived.get_json()["state"]
    assert any(item["name"] == "Sam" for item in state["waitingQueue"]) or state["techs"]["Mia T"].get("current") == "Sam"


def test_remove_tech_requires_manager(client):
    client.post("/api/queue/action", json={"action": "upsert_tech", "name": "Mia T"})
    denied = client.post("/api/queue/action", json={"action": "remove_tech", "name": "Mia T"})
    assert denied.status_code == 401


def test_end_of_day_requires_manager_and_clears_queue(client):
    headers = _manager_headers(client)
    client.post("/api/queue/action", json={"action": "upsert_tech", "name": "Mia T"})
    client.post("/api/queue/action", json={"action": "add_customer", "name": "Jordan"})
    closed = client.post("/api/salon/end-of-day", json={}, headers=headers)
    assert closed.status_code == 200
    state = closed.get_json()["state"]
    assert state["waitingQueue"] == []
    assert state["techs"]["Mia T"]["status"] == "Offline"
