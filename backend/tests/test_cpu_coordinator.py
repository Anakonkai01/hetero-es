"""CPU-only admission and scheduling stay independent of numerical/GPU libraries."""

import copy

import pytest

from backend.device_models import SelfTest
from heteroes.product.cpu_coordinator import PROFILE, UPDATE_EVIDENCE
from labkit import boot, enable, pair
from test_v3_study import assets, configuration, qualify_v3, v3_study as study_fixture


@pytest.fixture
def v3_study(tmp_path):
    yield from study_fixture.__wrapped__(tmp_path)


def profile():
    return {
        "passed": True,
        "coordinator": True,
        "gpuName": "CPU coordinator",
        "vramTotalMb": 0,
        "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
        "platform": "linux",
        "runtimeProfile": PROFILE,
        "recipeVersions": [3],
        "qualifiedModelHashes": [],
        "compatibility": {"updateKnownAnswer": dict(UPDATE_EVIDENCE)},
    }


@pytest.mark.parametrize("platform", ["linux", "windows"])
def test_cpu_profile_uses_only_the_pinned_update_evidence(platform):
    data = {**profile(), "platform": platform}
    assert SelfTest(**data).coordinator is True
    for changes in (
        {"passed": False},
        {"coordinator": False},
        {"recipeVersions": [1]},
        {"qualifiedModelHashes": ["a" * 64]},
        {"vramTotalMb": 1},
        {"gpuUUID": "GPU-00000000-0000-0000-0000-000000000001"},
        {"compatibility": {}},
    ):
        with pytest.raises(ValueError):
            SelfTest(**{**data, **changes})
    for key in UPDATE_EVIDENCE:
        altered = copy.deepcopy(data)
        altered["compatibility"]["updateKnownAnswer"][key] = "wrong"
        with pytest.raises(ValueError):
            SelfTest(**altered)


def enroll_cpu(lab):
    client, _, _, admin = lab
    code = client.post("/api/v1/devices/pairing-codes", headers=admin).json()["code"]
    response = client.post(
        "/api/v1/device/enroll",
        json={
            "code": code,
            "workerId": "cpu",
            "displayName": "CPU coordinator",
            "computeUrl": "http://100.64.0.2:8769",
            "selfTest": profile(),
        },
    )
    assert response.status_code == 201, response.text
    device = response.json()
    auth = {"Authorization": "Bearer " + device["deviceToken"]}
    assert (
        client.patch(
            "/api/v1/platform/devices/" + device["deviceId"],
            headers=admin,
            json={"approved": True, "workspaceId": "lab"},
        ).status_code
        == 200
    )
    boot(client, auth, "boot-1")
    return device, auth


def test_cpu_is_a_coordinator_but_never_a_worker(lab):
    client, _, runtime, admin = lab
    cpu, _ = enroll_cpu(lab)
    gpu, _ = pair(lab, "gpu")
    cap = client.get("/api/v1/capabilities", headers=admin).json()
    assert cpu["deviceId"] in {d["deviceId"] for d in cap["coordinatorDevices"]}
    assert cpu["workerId"] not in cap["workerIds"]
    assert cpu["workerId"] not in {d["workerId"] for d in client.get("/api/v1/workers", headers=admin).json()}
    assert gpu["workerId"] in runtime.capabilities()["workerIds"]


def test_v3_cpu_coordinator_skips_text_qualification_and_keeps_ownership(v3_study):
    client, admin, _ = v3_study
    store = client.app.state.store
    runtime = store.runtime
    lab = (client, store, runtime, admin)
    model, data = assets(v3_study)
    cpu, cpu_auth = enroll_cpu(lab)
    gpu, gpu_auth = pair(lab, "gpu")
    gpu_profile = next(d["selfTest"] for d in runtime.devices() if d["deviceId"] == gpu["deviceId"])
    # Only the GPU qualifies the model; CPU generated texts need not match it.
    qualify_v3(client, gpu_auth, gpu_profile, model)
    enable(lab, cpu, cpu_auth)
    enable(lab, gpu, gpu_auth)
    probe = client.post(
        f"/api/v1/models/{model['id']}/qualifications", headers=admin, json={"deviceId": cpu["deviceId"]}
    )
    assert probe.status_code == 409
    config = {**configuration(gpu, model, data), "coordinatorDeviceId": cpu["deviceId"]}
    response = client.post("/api/v1/experiments", headers=admin, json=config)
    assert response.status_code == 200, response.text
    run = response.json()["experimentId"]
    assert client.post(f"/api/v1/experiments/{run}/submit", headers=admin).status_code == 200
    store.dispatch_once()
    assert store.get(run)["status"] == "STARTING", store.get(run).get("waitingReason")
    assignment = runtime.runs()[0]
    with store.db() as db:
        _, assignment = runtime._assignment(db, assignment["assignmentId"])
    assert assignment["workerDevices"] == {"gpu": gpu["deviceId"]}
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM device_reservations").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM physical_reservations").fetchone()[0] == 1
    # The CPU reservation must not look like an unknown legacy GPU or stall unrelated GPU work.
    other, other_auth = pair(lab, "other")
    enable(lab, other, other_auth)
    from labkit import queued

    second = queued(lab, other)
    store.dispatch_once()
    assert store.get(second)["status"] == "STARTING", store.get(second).get("waitingReason")
    # CPU worker selection is refused even though it belongs to the workspace.
    bad = client.post("/api/v1/experiments", headers=admin, json={**config, "workerIds": ["cpu"]})
    assert bad.status_code == 422


def test_cpu_profile_cannot_replace_a_reserved_legacy_gpu(lab):
    client, store, runtime, _ = lab
    gpu, auth = pair(lab)
    original = runtime.devices()[0]["selfTest"]
    boot(client, auth, "boot-1", selfTest={**original, "gpuUUID": None})
    # Model an existing legacy assignment: it owns a device without a physical UUID.
    with store.db() as db:
        db.execute("INSERT INTO device_reservations VALUES (?,?)", (gpu["deviceId"], "test-legacy"))
    response = client.post("/api/v1/device/poll", headers=auth, json={"bootId": "boot-1", "selfTest": profile()})
    assert response.status_code == 409


def test_role_configuration_accepts_a_small_gpu_coordinator(lab):
    client, _, runtime, admin = lab
    gpu, _ = pair(lab, coordinator=False)
    data = {**runtime.devices()[0]["selfTest"], "vramTotalMb": 6000, "coordinator": True}
    response = client.patch(
        "/api/v1/devices/" + gpu["deviceId"] + "/configuration",
        headers=admin,
        json={"computeUrl": "http://100.64.0.1:8769", "selfTest": data},
    )
    assert response.status_code == 200, response.text
