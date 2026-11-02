"""OIDC identity never links by username or revives restricted accounts; local/device flows stay separate."""

import json
import time

from fastapi.testclient import TestClient
import pytest

from backend.apps.factory import create_app
from backend.services.devices import AgentRuntime
from test_oidc import ISSUER, CLIENT, jwks_server, signed, keys as keys
from test_recovery_storage import Objects, manifest
from labkit import pair


@pytest.fixture
def oidc_lab(tmp_path, keys):
    with jwks_server(keys) as server:
        app = create_app(
            tmp_path / "cloud.sqlite",
            {},
            AgentRuntime(Objects()),
            dispatch=False,
            auth_mode="oidc",
            oidc_issuer=ISSUER,
            oidc_jwks_url=server.url,
        )
        with TestClient(app) as client:
            yield client, app.state.store, app.state.store.runtime


def headers(keys, **claims):
    return {"Authorization": "Bearer " + signed(keys[0], **claims), "X-Workspace-Id": "lab"}


def test_first_identity_is_pending_without_local_session_or_password(oidc_lab, keys):
    client, store, _ = oidc_lab
    response = client.get("/api/v1/auth/session", headers=headers(keys))
    assert response.status_code == 200
    profile = response.json()["user"]
    assert profile["userId"] == "kc:subject-1" and profile["username"] == "researcher"
    assert profile["accountStatus"] == "PENDING" and not profile["platformAdmin"]
    assert response.json()["workspaces"] == [] and "accessToken" not in response.json()
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert db.execute("SELECT hash FROM users WHERE id=:p0", ("kc:subject-1",)).fetchone()[0] == "!oidc"
    assert client.get("/api/v1/capabilities", headers=headers(keys)).status_code == 403


def test_realm_admin_bootstrap_and_durable_approval_restrictions(oidc_lab, keys):
    client, store, _ = oidc_lab
    admin = headers(keys, sub="administrator", preferred_username="realm-admin", realm_access={"roles": ["lab-admin"]})
    response = client.get("/api/v1/auth/session", headers=admin)
    profile = response.json()["user"]
    assert profile["accountStatus"] == "ACTIVE" and profile["platformAdmin"] and profile["canCreateWorkspace"]
    assert response.json()["workspaces"][0]["role"] == "ADMIN"
    assert client.get("/api/v1/platform/users", headers=admin).status_code == 200
    for status in ["SUSPENDED", "REJECTED"]:
        with store.db() as db:
            profile["accountStatus"] = status
            db.execute("UPDATE users SET profile=:p0 WHERE id=:p1", (json.dumps(profile), profile["userId"]))
        result = client.get("/api/v1/auth/session", headers=admin).json()["user"]
        assert result["accountStatus"] == status and not result["platformAdmin"]
        assert client.get("/api/v1/platform/users", headers=admin).status_code == 403


def test_username_collision_cannot_link_or_take_over_any_identity(oidc_lab, keys):
    client, store, _ = oidc_lab
    original = client.get("/api/v1/auth/session", headers=headers(keys)).json()["user"]
    result = client.get("/api/v1/auth/session", headers=headers(keys, sub="other-subject"))
    assert result.status_code == 409 and store.profile("kc:other-subject") is None
    assert store.profile(original["userId"]) == original
    local = {
        "userId": "local-owner",
        "username": "local-name",
        "displayName": "Owner",
        "accountStatus": "ACTIVE",
        "platformAdmin": True,
    }
    with store.db() as db:
        db.execute(
            "INSERT INTO users(id,hash,profile) VALUES (:p0,:p1,:p2)", ("local-owner", "!unit", json.dumps(local))
        )
    result = client.get("/api/v1/auth/session", headers=headers(keys, sub="another", preferred_username="local-name"))
    assert result.status_code == 409 and store.profile("local-owner") == local


def test_approved_account_and_identity_survive_new_requests_without_role_escalation(oidc_lab, keys):
    client, store, _ = oidc_lab
    profile = client.get("/api/v1/auth/session", headers=headers(keys)).json()["user"]
    with store.db() as db:
        profile.update(accountStatus="ACTIVE", canCreateWorkspace=True)
        db.execute("UPDATE users SET profile=:p0 WHERE id=:p1", (json.dumps(profile), profile["userId"]))
    result = client.get("/api/v1/auth/session", headers=headers(keys, preferred_username="renamed")).json()["user"]
    assert result["userId"] == profile["userId"] and result["username"] == "renamed"
    assert result["accountStatus"] == "ACTIVE" and result["canCreateWorkspace"] and not result["platformAdmin"]


@pytest.mark.parametrize("path", ["login", "register", "password", "revoke-other-sessions"])
def test_local_auth_endpoints_are_guided_404_even_without_auth_or_valid_body(oidc_lab, path):
    client, store, _ = oidc_lab
    response = client.post("/api/v1/auth/" + path, json={})
    assert response.status_code == 404 and "HeteroES ID" in response.json()["message"]
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_role_removal_drops_platform_permission_and_device_token_protocol_is_unchanged(oidc_lab, keys):
    client, store, _ = oidc_lab
    admin = headers(keys, realm_access={"roles": ["lab-admin"]})
    profile = client.get("/api/v1/auth/session", headers=admin).json()["user"]
    device, device_headers = pair((client, store, store.runtime, admin), "oidc-device")
    assert client.post("/api/v1/device/poll", headers=device_headers, json={"bootId": "boot-1"}).status_code != 401
    assert client.get("/api/v1/auth/session", headers=device_headers).status_code == 401
    result = client.get("/api/v1/auth/session", headers=headers(keys)).json()["user"]
    assert not result["platformAdmin"] and result["userId"] == profile["userId"]
    assert client.get("/api/v1/platform/users", headers=headers(keys)).status_code == 403


def ready_artifact(client, store, keys, **claims):
    auth = headers(keys, realm_access={"roles": ["lab-admin"]}, **claims)
    profile = client.get("/api/v1/auth/session", headers=auth).json()["user"]
    rid = "c" * 32
    m = manifest()
    m.update(runId=rid, final=True)
    body = {
        "experimentId": rid,
        "ownerUserId": profile["userId"],
        "workspaceId": "lab",
        "status": "COMPLETED",
        "modelVersion": m["childWeightsSha256"],
    }
    with store.db() as db:
        db.execute(
            "INSERT INTO experiments(id,owner,body,snapshot) VALUES (:p0,:p1,:p2,NULL)",
            (rid, profile["userId"], json.dumps(body)),
        )
    plan = client.post("/api/v1/experiments/" + rid + "/recovery-import", headers=auth, json=m)
    assert plan.status_code == 200
    for obj in plan.json()["objects"]:
        client.app.state.storage.backend.put(obj["key"], b"weights")
    client.app.state.storage.verify(m["pointId"])
    return auth, rid + "." + m["childWeightsSha256"] + ".bin", profile


def test_oidc_download_ticket_needs_no_local_session_and_remains_single_use(oidc_lab, keys):
    client, store, _ = oidc_lab
    auth, artifact, _ = ready_artifact(client, store, keys)
    response = client.post("/api/v1/artifacts/" + artifact + "/download-ticket", headers=auth)
    assert response.status_code == 200
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert db.execute("SELECT session_digest FROM cloud_downloads").fetchone()[0].startswith("oidc:")
    path = response.json()["downloadUrl"]
    assert client.get(path, follow_redirects=False).status_code == 303
    assert client.get(path, follow_redirects=False).status_code == 401


@pytest.mark.parametrize("restriction", ["expiry", "suspended", "membership", "logout"])
def test_oidc_download_ticket_rechecks_expiry_account_membership_and_logout(oidc_lab, keys, restriction, monkeypatch):
    client, store, _ = oidc_lab
    expiry = time.time() + 20
    auth, artifact, profile = ready_artifact(client, store, keys, exp=expiry)
    response = client.post("/api/v1/artifacts/" + artifact + "/download-ticket", headers=auth)
    assert response.status_code == 200
    if restriction == "expiry":
        monkeypatch.setattr("backend.services.recovery_storage.time.time", lambda: expiry + 1)
    elif restriction == "logout":
        assert client.post("/api/v1/auth/logout", headers=auth).status_code == 204
    else:
        with store.db() as db:
            if restriction == "suspended":
                profile["accountStatus"] = "SUSPENDED"
                db.execute("UPDATE users SET profile=:p0 WHERE id=:p1", (json.dumps(profile), profile["userId"]))
            else:
                db.execute("DELETE FROM memberships WHERE user_id=:p0", (profile["userId"],))
    assert client.get(response.json()["downloadUrl"], follow_redirects=False).status_code in [401, 403]


def test_external_session_revocation_points_to_identity_provider_instead_of_false_success(oidc_lab, keys):
    client, store, _ = oidc_lab
    administrator = headers(
        keys, sub="admin-for-revoke", preferred_username="revoke-admin", realm_access={"roles": ["lab-admin"]}
    )
    client.get("/api/v1/auth/session", headers=administrator)
    client.get("/api/v1/auth/session", headers=headers(keys))
    result = client.post("/api/v1/platform/users/kc:subject-1/revoke-sessions", headers=administrator)
    assert result.status_code == 404 and "HeteroES ID" in result.json()["message"]


def test_invalid_mode_or_missing_authority_rejected_before_database_initialization(tmp_path):
    for options in [{"auth_mode": "unknown"}, {"auth_mode": "oidc"}]:
        with pytest.raises(ValueError):
            create_app(tmp_path / "unused.sqlite", {}, AgentRuntime(), dispatch=False, **options)
    assert not (tmp_path / "unused.sqlite").exists()


def test_cloud_factory_does_not_seed_legacy_password_accounts(tmp_path, keys):
    with jwks_server(keys) as server:
        app = create_app(
            tmp_path / "seed.sqlite",
            {"legacy": "unused-fixture-secret"},
            AgentRuntime(),
            dispatch=False,
            auth_mode="oidc",
            oidc_issuer=ISSUER,
            oidc_jwks_url=server.url,
        )
        with TestClient(app) as client:
            assert app.state.store.profile("legacy") is None
            assert client.post("/api/v1/auth/login", json={}).status_code == 404


def test_external_password_sentinel_cannot_authenticate_through_local_service(oidc_lab, keys):
    from backend.core.errors import ServiceError

    client, store, _ = oidc_lab
    client.get("/api/v1/auth/session", headers=headers(keys))
    with pytest.raises(ServiceError) as error:
        store.accounts.authenticate("researcher", "unused", store.accounts.session)
    assert error.value.status_code == 401
