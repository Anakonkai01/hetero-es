"""The lab-wide event list (GSM8K demo tier 2: HTTP 524 while a run was busy). It reads in one database session, can be
narrowed to one experiment and to the newest N events."""

import contextlib
import json

from labkit import draft, login


def runs_with_events(client, store, admin, count=3, per_run=5):
    runs = []
    for index in range(count):
        r = draft(client, admin, name=f"run {index}")
        assert r.status_code == 200, r.text
        rid = r.json()["experimentId"]
        events = [{"event": "generation_committed", "generation": g, "t": 1000 * index + g} for g in range(per_run)]
        with store.db() as db:
            db.execute("UPDATE experiments SET snapshot=? WHERE id=?", (json.dumps({"events": events}), rid))
        runs.append(rid)
    return runs


def test_the_event_list_reads_in_one_session_and_can_be_narrowed(setup, monkeypatch):
    client, store, _ = setup
    admin = login(client, "admin")
    runs = runs_with_events(client, store, admin)
    sessions = []
    original = store.db

    @contextlib.contextmanager
    def counted():
        sessions.append(1)
        with original() as db:
            yield db

    monkeypatch.setattr(store, "db", counted)
    everything = client.get("/api/v1/events", headers=admin)
    assert everything.status_code == 200, everything.text
    assert len(everything.json()) == 15
    for_all = len(sessions)
    sessions.clear()
    one = client.get(f"/api/v1/events?experimentId={runs[1]}&limit=2", headers=admin).json()
    assert len(sessions) == for_all  # the number of sessions does not grow with the runs (it was two per run)
    assert [e["eventId"] for e in one] == [f"{runs[1]}.e3", f"{runs[1]}.e4"]
    assert client.get("/api/v1/events?experimentId=" + "f" * 32, headers=admin).status_code == 404
