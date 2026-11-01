"""Shared business authorization and validation do not require transport errors."""

from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from backend.core.errors import ServiceError
from backend.policies import active_profile, platform_profile
from backend.request_models import Configuration
from backend.validation import validate_configuration as legacy_validate


def test_shared_authorization_uses_plain_errors_and_rechecks_durable_access(lab):
    _, store, _, _ = lab
    with pytest.raises(ServiceError) as missing:
        active_profile(store, {"userId": "missing"})
    assert missing.value.status_code == 403
    profile = active_profile(store, {"userId": "admin"})
    assert platform_profile(profile) is profile
    with pytest.raises(ServiceError) as denied:
        platform_profile({"platformAdmin": False})
    assert denied.value.status_code == 403


def test_configuration_service_errors_and_legacy_http_errors_keep_the_same_contract():
    from backend.services.validation import validate_configuration

    config = Configuration(
        name="Layer fixture", modelName="fixture-model", workerIds=["worker"], coordinatorDeviceId="missing"
    )
    current = {"workspaceId": "lab"}
    dependencies = dict(
        store=None,
        runtime=SimpleNamespace(devices=lambda: []),
        registry=None,
        scoped=lambda c, w: c,
        capabilities=lambda: {},
    )
    with pytest.raises(ServiceError) as business:
        validate_configuration(config, current, **dependencies)
    with pytest.raises(HTTPException) as http:
        legacy_validate(config, current, **dependencies)
    assert business.value.status_code == http.value.status_code == 422
    assert business.value.detail == http.value.detail


def test_explicit_resume_clears_the_hold_and_old_maintenance_flags(lab):
    client, store, _, owner = lab
    with store.db() as db:
        for key, value in (
            ("dispatchHold", "true"),
            ("maintenanceId", '"old-fixture-maintenance"'),
            ("agentMaintenance", "true"),
        ):
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
    response = client.post(
        "/api/v1/platform/maintenance/resume", headers=owner, json={"workerConfigurationConfirmed": True}
    )
    assert response.status_code == 200 and response.json() == {"dispatchHeld": False}
    with store.db() as db:
        assert db.execute("SELECT value FROM settings WHERE key='dispatchHold'").fetchone()[0] == "false"
        assert (
            db.execute("SELECT count(*) FROM settings WHERE key IN ('maintenanceId','agentMaintenance')").fetchone()[0]
            == 0
        )
        assert db.execute("SELECT count(*) FROM audit WHERE action='MAINTENANCE_END'").fetchone()[0] == 1


def test_resume_keeps_hold_when_imported_queued_workers_are_not_configured(lab):
    from labkit import pair, queued

    client, store, runtime, owner = lab
    device, _ = pair(lab)
    run = queued(lab, device)
    body = store.get(run)
    body["workerIds"] = ["unknown-imported-worker"]
    with store.db() as db:
        store.save(db, body)
        db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("dispatchHold", "true"))
    response = client.post(
        "/api/v1/platform/maintenance/resume", headers=owner, json={"workerConfigurationConfirmed": True}
    )
    assert response.status_code == 409
    assert store.get(run)["status"] == "QUEUED" and runtime.runs() == []
    with store.db() as db:
        assert db.execute("SELECT value FROM settings WHERE key='dispatchHold'").fetchone()[0] == "true"
        assert db.execute("SELECT count(*) FROM audit WHERE action='MAINTENANCE_END'").fetchone()[0] == 0


def test_workspace_scope_rechecks_stored_status_when_the_supplied_profile_is_stale(lab):
    import json
    from backend.services.access import AccessService

    _, store, runtime, _ = lab
    access = AccessService(store, runtime)
    stale = store.profile("admin")
    changed = {**stale, "accountStatus": "SUSPENDED"}
    with store.db() as db:
        db.execute("UPDATE users SET profile=? WHERE id=?", (json.dumps(changed), "admin"))
    with pytest.raises(ServiceError) as denied:
        access.scope(stale, "lab")
    assert denied.value.status_code == 403
    changed.update(accountStatus="ACTIVE", displayName="Updated fixture name")
    with store.db() as db:
        db.execute("UPDATE users SET profile=? WHERE id=?", (json.dumps(changed), "admin"))
    assert access.scope(stale, "lab")["displayName"] == "Updated fixture name"


def test_participant_list_hides_other_owners_runs_in_the_same_workspace(setup):
    from labkit import draft, login

    client, _, _ = setup
    participant = login(client, "participant")
    admin = login(client, "admin")
    own = draft(client, participant, name="Participant visibility fixture")
    other = draft(client, admin, name="Administrator visibility fixture")
    assert own.status_code == other.status_code == 200
    own_id, other_id = own.json()["experimentId"], other.json()["experimentId"]
    visible = client.get("/api/v1/experiments", headers=participant)
    assert visible.status_code == 200
    assert {run["experimentId"] for run in visible.json()} == {own_id}
    administrator_view = client.get("/api/v1/experiments", headers=admin)
    assert administrator_view.status_code == 200
    assert {run["experimentId"] for run in administrator_view.json()} == {own_id, other_id}
