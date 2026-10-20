"""The platform administrator approves a device into a workspace of the device's OWNER (found 2026-10-20 in the isolated
r11 lab: the approval form offered only the administrator's own workspaces, so a researcher's GPU could not join the
researcher's lab)."""


def _researcher_with_lab(client, admin):
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"username": "res", "displayName": "Researcher", "password": "researcher-pass-1"},
        ).status_code
        == 201
    )
    user = next(u for u in client.get("/api/v1/platform/users", headers=admin).json() if u["username"] == "res")
    assert (
        client.patch(
            "/api/v1/platform/users/" + user["userId"],
            headers=admin,
            json={"accountStatus": "ACTIVE", "canCreateWorkspace": True},
        ).status_code
        == 200
    )
    token = client.post("/api/v1/auth/login", json={"username": "res", "password": "researcher-pass-1"}).json()
    headers = {"Authorization": "Bearer " + token["accessToken"]}
    workspace = client.post("/api/v1/workspaces", headers=headers, json={"name": "Research lab"}).json()
    return {**headers, "X-Workspace-Id": workspace["workspaceId"]}, workspace["workspaceId"]


def test_the_device_list_names_the_owners_workspaces_and_approval_uses_one(lab):
    client, _, _, admin = lab
    researcher, workspace = _researcher_with_lab(client, admin)
    code = client.post("/api/v1/devices/pairing-codes", headers=researcher).json()["code"]
    enrolled = client.post(
        "/api/v1/device/enroll",
        json={
            "code": code,
            "workerId": "res-gpu",
            "displayName": "Researcher GPU",
            "selfTest": {
                "passed": True,
                "coordinator": True,
                "gpuName": "GPU",
                "vramTotalMb": 12000,
                "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
                "gpuUUID": "GPU-" + "1" * 8 + "-2222-3333-4444-" + "5" * 12,
            },
            "computeUrl": "http://100.64.0.2:8765",
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    enrolled = enrolled.json()
    listed = next(d for d in client.get("/api/v1/platform/devices", headers=admin).json() if d["workerId"] == "res-gpu")
    assert listed["ownerWorkspaces"] == [{"workspaceId": workspace, "name": "Research lab"}]
    approved = client.patch(
        "/api/v1/platform/devices/" + enrolled["deviceId"],
        headers=admin,
        json={"approved": True, "workspaceId": workspace},
    )
    assert approved.status_code == 200 and approved.json()["workspaceId"] == workspace


def test_the_owners_view_does_not_list_workspaces_of_other_people(lab):
    client, _, _, admin = lab
    researcher, _ = _researcher_with_lab(client, admin)
    for device in client.get("/api/v1/devices", headers=researcher).json():
        assert "ownerWorkspaces" not in device


def test_the_coordinator_choice_shows_the_name_the_owner_gave(lab):
    from labkit import enable, pair

    client, _, _, admin = lab
    enable(lab, *pair(lab, "gpu-alias"))
    [device] = client.get("/api/v1/capabilities", headers=admin).json()["coordinatorDevices"]
    assert device["workerId"] == "gpu-alias" and device["displayName"] == "gpu-alias"


def test_a_workspace_default_coordinator_is_offered_first_and_must_qualify(lab):
    from labkit import enable, pair

    client, _, _, admin = lab
    enable(lab, *pair(lab, "worker-only", coordinator=False))
    coordinator, _ = pair(lab, "coordinator-gpu")
    assert client.get("/api/v1/capabilities", headers=admin).json()["defaultCoordinatorDeviceId"] is None
    refused = client.patch(
        "/api/v1/workspaces/lab/default-coordinator",
        headers=admin,
        json={
            "deviceId": next(
                d["deviceId"]
                for d in client.get("/api/v1/platform/devices", headers=admin).json()
                if d["workerId"] == "worker-only"
            )
        },
    )
    assert refused.status_code == 422
    chosen = client.patch(
        "/api/v1/workspaces/lab/default-coordinator", headers=admin, json={"deviceId": coordinator["deviceId"]}
    )
    assert chosen.status_code == 200
    assert (
        client.get("/api/v1/capabilities", headers=admin).json()["defaultCoordinatorDeviceId"]
        == coordinator["deviceId"]
    )
    assert (
        client.patch("/api/v1/workspaces/lab/default-coordinator", headers=admin, json={"deviceId": None}).status_code
        == 200
    )
    assert client.get("/api/v1/capabilities", headers=admin).json()["defaultCoordinatorDeviceId"] is None


def test_a_revoked_default_coordinator_is_no_longer_offered(lab):
    from labkit import pair

    client, _, _, admin = lab
    coordinator, _ = pair(lab, "coordinator-gpu")
    client.patch(
        "/api/v1/workspaces/lab/default-coordinator", headers=admin, json={"deviceId": coordinator["deviceId"]}
    )
    client.patch("/api/v1/platform/devices/" + coordinator["deviceId"], headers=admin, json={"approved": False})
    assert client.get("/api/v1/capabilities", headers=admin).json()["defaultCoordinatorDeviceId"] is None
