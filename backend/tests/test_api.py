from pathlib import Path

import pytest

from backend.store import Store
from backend.errors import RuntimeRejected
from labkit import draft, login, submitted


def test_real_session_revocation_and_workspace_enforcement(setup):
    client, _, _ = setup
    assert client.get("/api/v1/experiments").status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    headers = login(client, "admin")
    assert client.get("/api/v1/experiments", headers={**headers, "X-Workspace-Id": "another"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/session", headers=headers).status_code == 401


def test_participant_cannot_read_or_cancel_admin_run(setup):
    client, _, _ = setup
    admin, participant = login(client, "admin"), login(client, "participant")
    run_id = draft(client, admin).json()["experimentId"]
    assert client.get("/api/v1/experiments", headers=participant).json() == []
    for suffix in ("", "/generations"):
        assert client.get("/api/v1/experiments/" + run_id + suffix, headers=participant).status_code == 404
    assert client.post(f"/api/v1/experiments/{run_id}/cancel", headers=participant).status_code == 404
    own = draft(client, participant).json()["experimentId"]
    assert client.get(f"/api/v1/experiments/{own}", headers=admin).status_code == 200


def test_runs_on_the_same_gpu_wait_in_order_and_submit_is_idempotent(setup):
    # Release after completion is covered by test_admission_hold.py (it needs the agents' drain reports).
    client, store, runtime = setup
    headers = login(client, "admin")
    ids = [draft(client, headers, name=f"Run {i}").json()["experimentId"] for i in range(2)]
    for run_id in ids:
        assert client.post(f"/api/v1/experiments/{run_id}/submit", headers=headers).status_code == 200
    client.post(f"/api/v1/experiments/{ids[0]}/submit", headers=headers)
    store.dispatch_once()
    store.dispatch_once()
    assert submitted(runtime) == ids[:1]
    assert store.get(ids[1])["status"] == "QUEUED"
    assert "release" in store.get(ids[1])["waitingReason"]


def test_queued_cancel_never_contacts_runtime(setup):
    client, store, runtime = setup
    headers = login(client, "participant")
    run_id = draft(client, headers).json()["experimentId"]
    client.post(f"/api/v1/experiments/{run_id}/submit", headers=headers)
    assert client.post(f"/api/v1/experiments/{run_id}/cancel", headers=headers).json()["status"] == "CANCELLED"
    store.dispatch_once()
    assert submitted(runtime) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"schedulerPolicy": "capacity-weighted"},
        {"syncMode": "asynchronous"},
        {"workerIds": ["unknown"]},
        {"candidatesPerGeneration": 1},
        {"sigma": 0},
        {"datasetIds": ["fake"]},
    ],
)
def test_invalid_or_unsupported_config_rejected(setup, changes):
    client, _, _ = setup
    assert draft(client, login(client, "admin"), **changes).status_code == 422


def test_config_is_immutable_after_submission(setup):
    client, _, _ = setup
    headers = login(client, "admin")
    run = draft(client, headers).json()
    client.post(f"/api/v1/experiments/{run['experimentId']}/submit", headers=headers)
    assert (
        client.patch(
            f"/api/v1/experiments/{run['experimentId']}", json={"name": "changed"}, headers=headers
        ).status_code
        == 409
    )


def test_credentials_are_hashed_and_no_lease_secrets_in_product(setup):
    client, store, _ = setup
    headers = login(client, "admin")
    assert "test-admin-pass" not in Path(store.path).read_bytes().decode("latin1")
    response = draft(client, headers)
    assert "lease_token" not in response.text
    assert "runtime_token" not in response.text


def test_restart_after_lost_start_response_uses_same_run_and_queue(setup):
    client, store, runtime = setup
    headers = login(client, "admin")
    run_id = draft(client, headers).json()["experimentId"]
    client.post(f"/api/v1/experiments/{run_id}/submit", headers=headers)
    original = runtime.submit

    def lost(config):
        original(config)
        raise TimeoutError("response lost after runtime accepted")

    runtime.submit = lost
    store.dispatch_once()  # the dispatcher keeps going and reports the error instead of raising it
    assert store.last_error == "TimeoutError"
    assert store.get(run_id)["status"] == "STARTING"
    runtime.submit = original
    restarted = Store(store.path, {}, runtime)
    restarted.dispatch_once()
    assert restarted.last_error is None
    assert restarted.get(run_id)["status"] == "STARTING"  # until the coordinator reports
    assert submitted(runtime) == [run_id]  # the retry found the frozen assignment instead of making a second one
    assert login(client, "admin")  # existing hashes and sessions survive restart


def test_child_objects_and_downloads_share_experiment_authorization(setup):
    client, store, runtime = setup
    admin, participant = login(client, "admin"), login(client, "participant")
    run_id = draft(client, admin).json()["experimentId"]
    client.post(f"/api/v1/experiments/{run_id}/submit", headers=admin)
    store.dispatch_once()
    for route in (
        f"/generations/{run_id}.g0/candidates",
        f"/candidates/{run_id}.g0.c0",
        f"/attempts/{run_id}.g0.c0.a1",
        f"/artifacts/{run_id}.config.json/download",
    ):
        assert client.get("/api/v1" + route, headers=participant).status_code == 404
    assert client.get("/api/v1/events", headers=participant).json() == []
    assert client.get("/api/v1/artifacts", headers=participant).json() == []


def test_rejected_start_fails_truthfully_and_releases_queue_claim(setup):
    client, store, runtime = setup
    headers = login(client, "admin")
    run_id = draft(client, headers).json()["experimentId"]
    client.post(f"/api/v1/experiments/{run_id}/submit", headers=headers)

    def rejected(_):
        raise RuntimeRejected("Worker quarantined")

    runtime.submit = rejected
    store.dispatch_once()
    assert store.get(run_id)["status"] == "FAILED"
    assert store.get(run_id)["failureReason"] == "Worker quarantined"
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM queue").fetchone()[0] == 0
