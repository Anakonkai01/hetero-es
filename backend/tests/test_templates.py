"""Saved experiment settings ("templates"): per workspace, validated, never carrying ids that can go stale."""

import pytest

from labkit import login
from test_lab import register, activate

GOOD = {
    "task": "arith16",
    "maxGenerations": 3,
    "candidatesPerGeneration": 12,
    "alpha": 0.001,
    "sigma": 0.001,
    "decodeEngine": "hf_generate",
    "schedulerPolicy": "greedy",
    "syncMode": "synchronous",
    "workerIds": ["5070ti", "3060"],
    "backupPolicy": {"interval": 1, "retain": 3},
}


def create(client, headers, name="Demo 3x12", config=None):
    return client.post(
        "/api/v1/experiment-templates",
        json={"name": name, "config": config if config is not None else GOOD},
        headers=headers,
    )


def test_a_template_is_saved_listed_and_returned_with_its_settings(setup):
    client, _, _ = setup
    admin = login(client, "admin")
    created = create(client, admin)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Demo 3x12" and body["config"] == GOOD and body["templateId"] and body["ownerName"]
    listed = client.get("/api/v1/experiment-templates", headers=admin).json()
    assert [t["templateId"] for t in listed] == [body["templateId"]]
    assert client.get("/api/v1/experiment-templates").status_code == 401


def test_templates_are_private_to_their_workspace(setup):
    client, _, _ = setup
    admin = login(client, "admin")
    create(client, admin)
    other = client.post("/api/v1/workspaces", json={"name": "Second lab"}, headers=admin).json()
    elsewhere = {**admin, "X-Workspace-Id": other["workspaceId"]}
    assert client.get("/api/v1/experiment-templates", headers=elsewhere).json() == []
    stranger = login(client, "participant")
    stranger = {**stranger, "X-Workspace-Id": other["workspaceId"]}
    assert client.get("/api/v1/experiment-templates", headers=stranger).status_code == 403


def test_only_known_settings_with_plain_values_are_accepted(setup):
    client, _, _ = setup
    admin = login(client, "admin")
    for bad in (
        {"datasetIds": ["x"]},
        {"modelArtifactId": "m"},
        {"coordinatorDeviceId": "d"},
        {"name": "x"},
        {"maxGenerations": "many"},
        {"maxGenerations": True},
        {"candidatesPerGeneration": 2.5},
        {"alpha": True},
        {"maxGenerations": 0},
        {"maxGenerations": 100000},
        {"candidatesPerGeneration": 1},
        {"alpha": -1},
        {"workerIds": "a"},
        {"workerIds": [1]},
        {"workerIds": ["x"] * 100},
        {"backupPolicy": {"interval": 0, "retain": 1}},
        {"backupPolicy": {"interval": 1}},
        {"decodeEngine": {"$set": 1}},
        {"task": "x" * 500},
        {"schedulerPolicy": "secret"},
    ):
        reply = create(client, admin, config={**GOOD, **bad})
        assert reply.status_code == 422, (bad, reply.text)
    assert create(client, admin, config={}).status_code == 422, "an empty template is useless"


def test_names_are_trimmed_unique_per_workspace_and_limited(setup):
    client, _, _ = setup
    admin = login(client, "admin")
    assert create(client, admin, name="   ").status_code == 422
    assert create(client, admin, name="ab").status_code == 422
    assert create(client, admin, name="x" * 101).status_code == 422
    first = create(client, admin, name="  Same name  ")
    assert first.status_code == 201 and first.json()["name"] == "Same name"
    assert create(client, admin, name="same NAME").status_code == 409
    for number in range(49):
        assert create(client, admin, name=f"Template {number:02d}").status_code == 201
    assert create(client, admin, name="One too many").status_code == 422


def test_the_owner_and_workspace_administrators_may_delete_others_may_not(setup):
    client, store, _ = setup
    admin = login(client, "admin")
    member_profile, member = register(client, "member1")
    activate(client, admin, member_profile)
    invite = client.post("/api/v1/workspaces/lab/invitations", json={"username": "member1"}, headers=admin)
    assert (
        client.post(f"/api/v1/my-invitations/{invite.json()['invitationId']}/accept", headers=member).status_code == 200
    )
    member = {**member, "X-Workspace-Id": "lab"}
    mine = create(client, member, name="Member template").json()
    theirs = create(client, admin, name="Admin template").json()
    assert client.delete(f"/api/v1/experiment-templates/{theirs['templateId']}", headers=member).status_code == 403
    assert client.delete(f"/api/v1/experiment-templates/{mine['templateId']}", headers=member).status_code == 204
    assert client.delete(f"/api/v1/experiment-templates/{theirs['templateId']}", headers=admin).status_code == 204
    assert client.delete(f"/api/v1/experiment-templates/{theirs['templateId']}", headers=admin).status_code == 404
    assert client.get("/api/v1/experiment-templates", headers=admin).json() == []


def test_a_template_of_another_workspace_cannot_be_deleted_by_id(setup):
    client, _, _ = setup
    admin = login(client, "admin")
    made = create(client, admin).json()
    other = client.post("/api/v1/workspaces", json={"name": "Second lab"}, headers=admin).json()
    elsewhere = {**admin, "X-Workspace-Id": other["workspaceId"]}
    assert client.delete(f"/api/v1/experiment-templates/{made['templateId']}", headers=elsewhere).status_code == 404
    assert len(client.get("/api/v1/experiment-templates", headers=admin).json()) == 1
