"""A notification's durable identity/read state survives projection catch-up."""

from labkit import draft, login
from test_notifications import finish, listing


def test_finished_run_notification_keeps_identity_and_read_state_on_refresh(setup):
    client, store, _ = setup
    admin = login(client, "admin")
    run = draft(client, admin).json()["experimentId"]
    finish(store, run)
    initial = listing(client, admin)
    [notification] = [item for item in initial["items"] if item["kind"] == "run.completed"]
    assert notification["read"] is False
    reply = client.post("/api/v1/notifications/read", json={"ids": [notification["id"]]}, headers=admin)
    assert reply.status_code == 200
    for _ in range(2):
        refreshed = listing(client, admin)
        [again] = [item for item in refreshed["items"] if item["kind"] == "run.completed"]
        assert again["id"] == notification["id"]
        assert again["read"] is True
        assert refreshed["unread"] == 0
