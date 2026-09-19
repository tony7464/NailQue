from nailque.catalog import build_service_details
from nailque.queue import empty_shared_state, sanitize_state_for_client, try_auto_assign


def test_auto_assign_pairs_available_tech_with_waiting_customer():
    state = empty_shared_state()
    state["techs"] = {
        "Mia T": {"status": "Available", "current": None, "startTime": None, "earnings": 0},
    }
    state["waitingQueue"] = [{"id": 1, "name": "Jordan", "arrival": 1, "requestedTech": "", "appointmentTime": None}]
    try_auto_assign(state)
    assert state["waitingQueue"] == []
    assert state["techs"]["Mia T"]["status"] == "Busy"
    assert state["techs"]["Mia T"]["current"] == "Jordan"


def test_public_state_never_includes_passwords():
    state = empty_shared_state()
    state["credentials"] = {
        "Mia T": {"identifier": "miat", "password": "super-secret", "mustChangePassword": True}
    }
    public = sanitize_state_for_client(state, include_credential_meta=True)
    assert "credentials" not in public
    assert public["credentialMeta"]["Mia T"]["identifier"] == "miat"
    assert "password" not in public["credentialMeta"]["Mia T"]


def test_service_details_ignore_invalid_indexes_and_addons():
    details = build_service_details([0, 999, "bad"], [{"name": "Art", "price": 12}, {"name": "", "price": 9}])
    assert details["selectedServiceIndexes"] == [0]
    assert details["customAddons"] == [{"name": "Art", "price": 12.0}]
    assert details["employeeShare"] == round(details["total"] * 0.6, 2)
