"""In-app notifications: a projection of what happened (accounts, devices, runs) for the people who must know."""

import json

from labkit import draft, enroll, login
from test_lab import register, activate


def listing(client, headers):
    reply = client.get("/api/v1/notifications", headers=headers)
    assert reply.status_code == 200, reply.text
    return reply.json()


def kinds(client, headers):
    return [item["kind"] for item in listing(client, headers)["items"]]


def finish(store, run_id, status="COMPLETED"):
    with store.db() as db:
        body = json.loads(db.execute("SELECT body FROM experiments WHERE id=?", (run_id,)).fetchone()[0])
        from backend.store import now

        db.execute(
            "UPDATE experiments SET body=? WHERE id=?",
            (json.dumps({**body, "status": status, "completedAt": now()}), run_id),
        )


def test_history_from_before_notifications_existed_does_not_flood_the_bell(setup):
    from backend.notifications import Notifications

    client, store, _ = setup
    admin = login(client, "admin")
    register(client, "early")
    old = draft(client, admin).json()["experimentId"]
    finish(store, old)
    with store.db() as db:  # a lab that has never had notifications
        db.execute("DELETE FROM settings WHERE key IN ('notificationCursor','notificationSince')")
    Notifications(store)  # the server starting up fixes the starting point
    assert listing(client, admin) == {"items": [], "unread": 0}
    assert listing(client, admin) == {"items": [], "unread": 0}, "a second look does not dig the history up either"
    with store.db() as db:
        assert (
            json.loads(db.execute("SELECT value FROM settings WHERE key='notificationCursor'").fetchone()[0])
            == db.execute("SELECT MAX(sequence) FROM audit").fetchone()[0]
        )
    assert client.get("/api/v1/notifications").status_code == 401
    register(client, "late")
    assert kinds(client, admin) == ["account.request"], "what happens after start-up is announced"


def test_a_restart_keeps_the_starting_point_so_nothing_is_missed(setup):
    from backend.notifications import Notifications

    client, store, _ = setup
    admin = login(client, "admin")
    register(client, "before-restart")
    Notifications(store)  # a second start-up must not move the starting point forward
    assert kinds(client, admin) == ["account.request"]


def test_a_new_account_request_reaches_administrators_only_and_only_once(setup):
    client, store, _ = setup
    admin, participant = login(client, "admin"), login(client, "participant")
    profile, _ = register(client, "newcomer")
    items = listing(client, admin)["items"]
    assert [i["kind"] for i in items] == ["account.request"]
    assert (
        items[0]["params"] == {"username": "newcomer", "displayName": "Newcomer"}
        and items[0]["target"] == "/operations"
        and items[0]["read"] is False
    )
    assert listing(client, admin)["unread"] == 1
    assert kinds(client, admin) == ["account.request"], "asking again does not repeat it"
    with store.db() as db:
        assert (
            json.loads(db.execute("SELECT value FROM settings WHERE key='notificationCursor'").fetchone()[0])
            == db.execute("SELECT MAX(sequence) FROM audit").fetchone()[0]
        ), "the starting point moves forward so the log is not rescanned"
    assert listing(client, participant)["items"] == []


def test_the_person_is_told_when_their_account_is_approved_declined_or_suspended(setup):
    client, store, _ = setup
    admin = login(client, "admin")
    listing(client, admin)
    profile, alice = register(client, "alice")
    listing(client, alice)
    activate(client, admin, profile)
    assert kinds(client, alice) == ["account.approved"]
    client.patch("/api/v1/platform/users/" + profile["userId"], json={"accountStatus": "SUSPENDED"}, headers=admin)
    listing(client, admin)  # any look catches up; a suspended person has no session left to look with
    with store.db() as db:
        recorded = [
            row[0]
            for row in db.execute(
                "SELECT kind FROM notifications WHERE user_id=? ORDER BY id DESC", (profile["userId"],)
            )
        ]
    assert recorded == ["account.suspended", "account.approved"], "newest first"
    bob_profile, bob = register(client, "bob")
    client.patch("/api/v1/platform/users/" + bob_profile["userId"], json={"accountStatus": "REJECTED"}, headers=admin)
    listing(client, admin)
    with store.db() as db:
        assert [
            row[0] for row in db.execute("SELECT kind FROM notifications WHERE user_id=?", (bob_profile["userId"],))
        ] == ["account.rejected"]


def test_a_run_that_ends_notifies_its_owner_with_the_outcome_and_a_link(setup):
    client, store, _ = setup
    admin, participant = login(client, "admin"), login(client, "participant")
    listing(client, admin)
    run = draft(client, admin, name="Overnight run").json()["experimentId"]
    other = draft(client, admin, name="Another run").json()["experimentId"]
    finish(store, run, "COMPLETED")
    finish(store, other, "FAILED")
    items = listing(client, admin)["items"]
    by_kind = {i["kind"]: i for i in items}
    assert set(by_kind) == {"run.completed", "run.failed"}
    assert (
        by_kind["run.completed"]["params"] == {"name": "Overnight run"}
        and by_kind["run.completed"]["target"] == f"/experiments/{run}"
    )
    assert listing(client, participant)["items"] == []
    finish(store, run, "COMPLETED")
    assert len(listing(client, admin)["items"]) == 2, "the same ending is not announced twice"
    third = draft(client, admin, name="Cancelled run").json()["experimentId"]
    finish(store, third, "CANCELLED")
    assert kinds(client, admin)[0] == "run.cancelled"


def test_marking_as_read_changes_the_count_and_only_my_own_notifications(setup):
    client, store, _ = setup
    admin, participant = login(client, "admin"), login(client, "participant")
    listing(client, admin)
    listing(client, participant)
    register(client, "one")
    register(client, "two")
    with store.db() as db:
        db.execute(
            "INSERT INTO notifications(user_id,kind,params,target,created,dedupe) VALUES ('participant-id-unknown','account.approved','{}','/x','2026-01-01','seed-1')"
        )
    data = listing(client, admin)
    assert data["unread"] == 2
    first, second = [i["id"] for i in data["items"]]
    assert client.post("/api/v1/notifications/read", json={"ids": [first]}, headers=participant).status_code == 200
    assert listing(client, admin)["unread"] == 2, "another person cannot mark mine"
    assert client.post("/api/v1/notifications/read", json={"ids": [first]}, headers=admin).status_code == 200
    assert listing(client, admin)["unread"] == 1
    assert [i["read"] for i in listing(client, admin)["items"]] == [True, False]
    assert client.post("/api/v1/notifications/read", json={"all": True}, headers=admin).status_code == 200
    assert listing(client, admin)["unread"] == 0
    with store.db() as db:
        assert (
            db.execute("SELECT read_at FROM notifications WHERE user_id='participant-id-unknown'").fetchone()[0] is None
        ), "someone else's notification stays unread"
    client.post("/api/v1/notifications/read", json={"all": True}, headers=participant)
    assert listing(client, admin)["unread"] == 0
    assert client.post("/api/v1/notifications/read", json={}, headers=admin).status_code == 422
    assert client.post("/api/v1/notifications/read", json={"ids": ["x"] * 500}, headers=admin).status_code == 422


def test_the_list_is_capped_and_unread_counts_everything_unread(setup):
    client, store, _ = setup
    from backend.throttle import Throttle

    client.app.state.registrations = Throttle(1000, 3600)
    admin = login(client, "admin")
    listing(client, admin)
    for number in range(30):
        register(client, f"person{number:02d}")
    data = client.get("/api/v1/notifications?limit=10", headers=admin).json()
    assert len(data["items"]) == 10 and data["unread"] == 30
    assert client.get("/api/v1/notifications?limit=0", headers=admin).status_code == 422
    assert client.get("/api/v1/notifications?limit=1000", headers=admin).status_code == 422


def test_a_device_waiting_for_approval_is_announced_to_administrators_while_it_is_still_waiting(setup):
    client, store, runtime = setup
    admin, participant = login(client, "admin"), login(client, "participant")
    listing(client, admin)  # the two approved devices of the fixture were enrolled too: no request for them
    enroll((client, store, runtime, admin), "quang-3060", name="Quang 3060")
    items = listing(client, admin)["items"]
    assert [(i["kind"], i["params"]) for i in items] == [("device.request", {"name": "Quang 3060"})]
    assert items[0]["target"] == "/operations"
    assert listing(client, participant)["items"] == []
