"""Public experiment boundaries still hold when the layers and SQL move."""

import json
import sqlite3

import pytest

from backend.db.transactions import begin_write
from labkit import draft, login


def test_queued_cancel_removes_the_entry_and_updates_remaining_fifo_position(setup):
    client, _, _ = setup
    admin = login(client, "admin")
    ids = [draft(client, admin, name=f"Queue contract {i}").json()["experimentId"] for i in range(2)]
    for run in ids:
        assert client.post(f"/api/v1/experiments/{run}/submit", headers=admin).status_code == 200
    assert client.post(f"/api/v1/experiments/{ids[0]}/cancel", headers=admin).status_code == 200
    queued = client.get("/api/v1/queue", headers=admin).json()
    assert [(row["experimentId"], row["position"]) for row in queued] == [(ids[1], 1)]


def test_queue_is_scoped_to_the_owner_unless_the_caller_is_an_administrator(setup):
    client, _, _ = setup
    admin, participant = login(client, "admin"), login(client, "participant")
    first = draft(client, admin).json()["experimentId"]
    second = draft(client, participant).json()["experimentId"]
    for run, headers in [(first, admin), (second, participant)]:
        assert client.post(f"/api/v1/experiments/{run}/submit", headers=headers).status_code == 200
    assert [row["experimentId"] for row in client.get("/api/v1/queue", headers=admin).json()] == [first, second]
    assert [row["experimentId"] for row in client.get("/api/v1/queue", headers=participant).json()] == [second]


def test_recorded_candidate_is_readable_by_owner_but_not_another_participant(setup):
    client, store, _ = setup
    admin, participant = login(client, "admin"), login(client, "participant")
    run = draft(client, admin).json()["experimentId"]
    candidate = run + ".g0.c0"
    snapshot = {
        "generations": [],
        "candidates": [{"candidateId": candidate}],
        "attempts": [],
        "events": [],
        "artifacts": [],
    }
    with store.db() as db:
        db.execute("UPDATE experiments SET snapshot=? WHERE id=?", (json.dumps(snapshot), run))
    path = f"/api/v1/candidates/{candidate}"
    assert client.get(path, headers=admin).json()["candidateId"] == candidate
    assert client.get(path, headers=participant).status_code == 404


def test_store_config_identity_is_order_independent_and_nonfinite_save_writes_nothing(setup):
    client, store, _ = setup
    body = draft(client, login(client, "admin")).json()
    metadata = {
        "experimentId",
        "workspaceId",
        "ownerUserId",
        "status",
        "cancelRequested",
        "modelVersion",
        "configHash",
        "createdAt",
        "completedGenerations",
    }
    config = {key: value for key, value in body.items() if key not in metadata}
    first = store.create("admin", config)
    second = store.create("admin", dict(reversed(list(config.items()))))
    assert first["configHash"] == second["configHash"] == body["configHash"]
    first["invalidMetric"] = float("nan")
    with store.db() as db:
        with pytest.raises(ValueError):
            store.save(db, first)
    assert "invalidMetric" not in store.get(first["experimentId"])


def test_explicit_write_claim_blocks_a_second_writer_before_the_first_change(tmp_path):
    path = tmp_path / "write-claim.sqlite"
    with sqlite3.connect(path, timeout=0.05) as first, sqlite3.connect(path, timeout=0.05) as second:
        first.execute("CREATE TABLE changes(id INTEGER)")
        begin_write(first)
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            second.execute("INSERT INTO changes VALUES (1)")
        first.rollback()
        second.execute("INSERT INTO changes VALUES (2)")
        second.commit()
        assert first.execute("SELECT id FROM changes").fetchall() == [(2,)]


def test_empty_event_view_and_unknown_run_are_distinct(lab):
    client, _, _, admin = lab
    assert client.get("/api/v1/events", headers=admin).json() == []
    assert client.get("/api/v1/events?experimentId=missing", headers=admin).status_code == 404


def test_held_submission_preserves_draft_and_queue_then_resumes_after_release(setup):
    client, store, _ = setup
    admin = login(client, "admin")
    run = draft(client, admin).json()["experimentId"]
    with store.db() as db:
        db.execute("UPDATE settings SET value=? WHERE key=?", ("true", "dispatchHold"))
    assert client.post(f"/api/v1/experiments/{run}/submit", headers=admin).status_code == 409
    assert store.get(run)["status"] == "DRAFT"
    assert client.get("/api/v1/queue", headers=admin).json() == []
    with store.db() as db:
        db.execute("UPDATE settings SET value=? WHERE key=?", ("false", "dispatchHold"))
    assert client.post(f"/api/v1/experiments/{run}/submit", headers=admin).status_code == 200
    assert store.get(run)["status"] == "QUEUED"
