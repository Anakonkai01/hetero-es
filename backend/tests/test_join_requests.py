"""A researcher asks to join a listed workspace; its administrator approves or rejects (owner decision 2026-10-20).
Invitations stay; an unlisted workspace is invisible and cannot be asked."""


def _user(client, admin, name):
    password = name + "-password-1"
    assert (
        client.post(
            "/api/v1/auth/register", json={"username": name, "displayName": name.title(), "password": password}
        ).status_code
        == 201
    )
    user = next(u for u in client.get("/api/v1/platform/users", headers=admin).json() if u["username"] == name)
    client.patch(
        "/api/v1/platform/users/" + user["userId"],
        headers=admin,
        json={"accountStatus": "ACTIVE", "canCreateWorkspace": True},
    )
    token = client.post("/api/v1/auth/login", json={"username": name, "password": password}).json()["accessToken"]
    return {"Authorization": "Bearer " + token}, user["userId"]


def _lab(client, headers, name="Open lab"):
    return client.post("/api/v1/workspaces", headers=headers, json={"name": name}).json()["workspaceId"]


def test_join_a_listed_workspace_after_its_administrator_approves(lab):
    client, _, _, admin = lab
    owner, _ = _user(client, admin, "owner")
    asker, asker_id = _user(client, admin, "asker")
    workspace = _lab(client, owner)
    assert client.get("/api/v1/listed-workspaces", headers=asker).json() == []
    assert client.post(f"/api/v1/workspaces/{workspace}/join-requests", headers=asker).status_code == 404
    assert (
        client.patch(f"/api/v1/workspaces/{workspace}/listing", headers=owner, json={"listed": True}).status_code == 200
    )
    [listed] = client.get("/api/v1/listed-workspaces", headers=asker).json()
    assert listed["workspaceId"] == workspace and listed["member"] is False and listed["requested"] is False
    request = client.post(f"/api/v1/workspaces/{workspace}/join-requests", headers=asker)
    assert request.status_code == 201
    assert client.post(f"/api/v1/workspaces/{workspace}/join-requests", headers=asker).status_code == 409
    assert client.get("/api/v1/listed-workspaces", headers=asker).json()[0]["requested"] is True
    # only the workspace's administrator sees and decides
    assert client.get(f"/api/v1/workspaces/{workspace}/join-requests", headers=asker).status_code == 403
    [pending] = client.get(f"/api/v1/workspaces/{workspace}/join-requests", headers=owner).json()
    assert pending["userId"] == asker_id and pending["username"] == "asker"
    decided = client.post(
        f"/api/v1/workspaces/{workspace}/join-requests/{pending['requestId']}", headers=owner, json={"approve": True}
    )
    assert decided.status_code == 200 and decided.json()["status"] == "APPROVED"
    session = client.get("/api/v1/auth/session", headers=asker).json()
    assert any(w["workspaceId"] == workspace and w["role"] == "PARTICIPANT" for w in session["workspaces"])
    assert client.get(f"/api/v1/workspaces/{workspace}/join-requests", headers=owner).json() == []
    assert client.get("/api/v1/listed-workspaces", headers=asker).json()[0]["member"] is True
    assert client.post(f"/api/v1/workspaces/{workspace}/join-requests", headers=asker).status_code == 409


def test_a_rejected_request_adds_no_member_and_may_be_asked_again(lab):
    client, _, _, admin = lab
    owner, _ = _user(client, admin, "owner")
    asker, _ = _user(client, admin, "asker")
    workspace = _lab(client, owner)
    client.patch(f"/api/v1/workspaces/{workspace}/listing", headers=owner, json={"listed": True})
    request_id = client.post(f"/api/v1/workspaces/{workspace}/join-requests", headers=asker).json()["requestId"]
    rejected = client.post(
        f"/api/v1/workspaces/{workspace}/join-requests/{request_id}", headers=owner, json={"approve": False}
    )
    assert rejected.json()["status"] == "REJECTED"
    session = client.get("/api/v1/auth/session", headers=asker).json()
    assert all(w["workspaceId"] != workspace for w in session["workspaces"])
    assert client.post(f"/api/v1/workspaces/{workspace}/join-requests", headers=asker).status_code == 201
    # unlisting hides the workspace again; a request already decided stays decided
    client.patch(f"/api/v1/workspaces/{workspace}/listing", headers=owner, json={"listed": False})
    assert client.get("/api/v1/listed-workspaces", headers=asker).json() == []


def test_only_a_workspace_administrator_lists_it(lab):
    client, _, _, admin = lab
    owner, _ = _user(client, admin, "owner")
    other, _ = _user(client, admin, "other")
    workspace = _lab(client, owner)
    assert (
        client.patch(f"/api/v1/workspaces/{workspace}/listing", headers=other, json={"listed": True}).status_code == 403
    )
