"""Managed configuration preserves raw prompting and versioned boxed scoring."""

import pytest

from test_v3_study import assets, configuration, qualify_v3, v3_study as study_fixture
from labkit import pair, enable


@pytest.fixture
def v3_study(tmp_path):
    yield from study_fixture.__wrapped__(tmp_path)


def test_raw_prompt_and_boxed_reward_reach_the_assignment(v3_study):
    client, admin, _ = v3_study
    store = client.app.state.store
    lab = client, store, store.runtime, admin
    gpu, auth = pair(lab)
    model, data = assets(v3_study)
    profile = client.get("/api/v1/devices", headers=admin).json()[0]["selfTest"]
    qualify_v3(client, auth, profile, model)
    enable(lab, gpu, auth)
    config = {
        **configuration(gpu, model, data),
        "promptFormat": "raw",
        "systemPrompt": None,
        "scorer": {
            "kind": "declarative",
            "name": "boxed-number",
            "version": 1,
            "codeSha256": None,
            "config": {"answerField": "level", "formatReward": 0.1},
        },
    }
    response = client.post("/api/v1/experiments", headers=admin, json=config)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["promptFormat"] == "raw" and run["scorer"]["config"]["formatReward"] == 0.1
    assert client.post(f"/api/v1/experiments/{run['experimentId']}/submit", headers=admin).status_code == 200
    store.dispatch_once()
    with store.db() as db:
        _, assignment = store.runtime._assignment(db, store.runtime.runs()[0]["assignmentId"])
    assert assignment["config"]["promptFormat"] == "raw"
    assert assignment["config"]["scorer"] == config["scorer"]
    for change in ({"promptFormat": "unknown"}, {"systemPrompt": "must not be ignored"}):
        assert client.post("/api/v1/experiments", headers=admin, json={**config, **change}).status_code == 422
    old = client.post("/api/v1/experiments", headers=admin, json=configuration(gpu, model, data))
    assert old.status_code == 200 and "promptFormat" not in old.json()
