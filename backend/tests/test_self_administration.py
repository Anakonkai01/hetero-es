"""Self lockout is refused even when another administrator exists."""

import pytest
from labkit import login


@pytest.fixture
def lab(setup):
    client, store, runtime = setup
    return client, store, runtime, login(client, "admin")


def accounts(lab):
    client, store, _, admin = lab
    users = {p["username"]: p["userId"] for p in client.get("/api/v1/platform/users", headers=admin).json()}
    other = users["participant"]
    assert (
        client.patch(f"/api/v1/platform/users/{other}", headers=admin, json={"platformAdmin": True}).status_code == 200
    )
    return users


@pytest.mark.parametrize(
    "changes",
    [
        {"accountStatus": "SUSPENDED"},
        {"accountStatus": "REJECTED"},
        {"platformAdmin": False},
        {"canCreateWorkspace": False},
    ],
)
def test_admin_cannot_remove_own_access_or_permissions(lab, changes):
    client, _, _, admin = lab
    users = accounts(lab)
    response = client.patch(f"/api/v1/platform/users/{users['admin']}", headers=admin, json=changes)
    assert response.status_code == 409
    assert client.get("/api/v1/platform/users", headers=admin).status_code == 200


def test_admin_uses_personal_security_api_instead_of_self_revoke(lab):
    client, _, _, admin = lab
    users = accounts(lab)
    assert client.post(f"/api/v1/platform/users/{users['admin']}/revoke-sessions", headers=admin).status_code == 409
    assert client.get("/api/v1/platform/users", headers=admin).status_code == 200


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_workspace_admin_cannot_remove_own_membership_or_role(lab, method):
    client, store, _, admin = lab
    users = accounts(lab)
    with store.db() as db:
        db.execute("INSERT OR REPLACE INTO memberships VALUES (?,?,?)", ("lab", users["participant"], "ADMIN"))
    path = f"/api/v1/workspaces/lab/members/{users['admin']}"
    response = (
        client.patch(path, headers=admin, json={"role": "PARTICIPANT"})
        if method == "PATCH"
        else client.delete(path, headers=admin)
    )
    assert response.status_code == 409
