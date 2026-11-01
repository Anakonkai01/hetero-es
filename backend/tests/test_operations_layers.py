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
