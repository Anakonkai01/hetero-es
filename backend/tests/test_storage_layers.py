"""Filesystem capability validation remains usable without an HTTP dependency."""

import pytest

from backend.core.errors import ServiceError
from backend.storage.local_backend import LocalBackend
from labkit import enable, pair, queued
from test_recovery_routes import lab as recovery_fixture
from test_recovery_storage import manifest


@pytest.fixture
def recovery_lab(tmp_path):
    yield from recovery_fixture.__wrapped__(tmp_path)


def test_signed_storage_grant_errors_are_plain_and_valid_grants_still_bind_method(tmp_path):
    backend = LocalBackend(tmp_path / "objects", tmp_path / "key", "http://127.0.0.1:18052")
    with pytest.raises(ServiceError) as invalid:
        backend.grant("invalid-fixture-capability", "PUT")
    assert invalid.value.status_code == 403
    key = "uploads/" + "a" * 64 + "/" + "b" * 32
    plan = backend.upload_plan(key, 7)
    token = plan["url"].rsplit("/", 1)[1]
    assert backend.grant(token, "PUT")["key"] == key
    with pytest.raises(ServiceError) as wrong_method:
        backend.grant(token, "GET")
    assert wrong_method.value.status_code == 403


def ready_ticket(lab):
    client, store, runtime, owner = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    run = queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    document = manifest()
    document["runId"] = run
    plan = client.post(
        "/api/v1/device/recovery-points",
        headers=auth,
        json={"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"], "manifest": document},
    )
    assert plan.status_code == 200
    storage = client.app.state.storage
    for obj in plan.json()["objects"]:
        storage.backend.put(obj["key"], b"weights")
    storage.verify(document["pointId"])
    ticket = client.post(f"/api/v1/artifacts/{run}.{document['childWeightsSha256']}.bin/download-ticket", headers=owner)
    assert ticket.status_code == 200
    assert set(ticket.json()) == {"downloadUrl"}
    return ticket.json()["downloadUrl"], ticket.cookies.get("heteroes-cloud-download")


def test_download_ticket_requires_its_cookie_and_remains_available_after_a_bad_cookie(recovery_lab):
    client, store, _, _ = recovery_lab
    path, secret = ready_ticket(recovery_lab)
    client.cookies.clear()
    assert client.get(path, follow_redirects=False).status_code == 401
    client.cookies.set("heteroes-cloud-download", "incorrect-fixture-cookie")
    assert client.get(path, follow_redirects=False).status_code == 401
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM cloud_downloads").fetchone()[0] == 1
    client.cookies.clear()
    client.cookies.set("heteroes-cloud-download", secret)
    downloaded = client.get(path, follow_redirects=False)
    assert downloaded.status_code == 303
    assert downloaded.headers["referrer-policy"] == "no-referrer"
    assert client.get(path, follow_redirects=False).status_code == 401


def test_expired_download_ticket_is_rejected_even_with_the_correct_cookie(recovery_lab):
    client, store, _, _ = recovery_lab
    path, _ = ready_ticket(recovery_lab)
    with store.db() as db:
        db.execute("UPDATE cloud_downloads SET expires=0")
    assert client.get(path, follow_redirects=False).status_code == 401
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM cloud_downloads").fetchone()[0] == 1
