"""A model probe owns its GPU until confirmed death; the CPU lab checks every signed repeat itself."""

from copy import deepcopy
import json

import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.product.model_qualification import PROFILE, SEED, _documents, cell_configs, reference_rows
from labkit import boot, enable, pair, queued
from test_v3_study import assets, configuration, qualify_v3, v3_study as study_fixture


@pytest.fixture
def v3_study(tmp_path):
    yield from study_fixture.__wrapped__(tmp_path)


def setup(study, alias="probe-gpu"):
    client, admin, _ = study
    store = client.app.state.store
    lab = client, store, store.runtime, admin
    device, auth = pair(lab, alias)
    auth = {
        **auth,
        "X-HeteroES-Agent-Commands": auth["X-HeteroES-Agent-Commands"] + ",QUALIFY_MODEL,CANCEL_MODEL_QUALIFICATION",
    }
    model, _ = assets(study)
    # This native profile qualified a different model. A report must add qualification without rewriting it.
    profile = next(d["selfTest"] for d in store.runtime.devices() if d["deviceId"] == device["deviceId"])
    qualify_v3(client, auth, profile, {"manifestHash": "f" * 64})
    enable(lab, device, auth)
    return lab, device, auth, model


def report_inputs(model):
    """Synthetic observations exercise admission, not GPU numerical compatibility."""
    manifest = model["manifest"]
    recipe, plan = _documents(manifest, "a" * 64, "b" * 64)
    common = {
        "recipeHash": canonical_json_hash(recipe),
        "modelManifestHash": model["manifestHash"],
        "parentSha256": "c" * 64,
        "restoredSha256": "c" * 64,
        "outputsHash": "d" * 64,
        "reward": 0.5,
    }
    positive = {**common, "perturbedSha256": "e" * 64}
    negative = {**common, "perturbedSha256": "f" * 64}
    reference = {
        "formatVersion": 1,
        "profile": PROFILE,
        "manifestHash": model["manifestHash"],
        "seed": SEED,
        "rows": reference_rows(),
        "cell": {
            "config": cell_configs(manifest["modelId"], manifest["revision"])["full"],
            "recipe": recipe,
            "plan": plan,
            "expected": positive,
            "negativeExpected": negative,
        },
    }
    return reference, {"1": [deepcopy(positive), deepcopy(positive)], "-1": [deepcopy(negative), deepcopy(negative)]}


def route(model):
    return f"/api/v1/models/{model['id']}/qualifications"


def start(lab, device, model):
    c, _, _, admin = lab
    response = c.post(route(model), headers=admin, json={"deviceId": device["deviceId"]})
    assert response.status_code == 201, response.text
    return response.json()


def finish(c, auth, job, model, **changes):
    reference, observations = report_inputs(model)
    return boot(
        c,
        auth,
        "boot-1",
        contribution=True,
        qualificationReports=[
            {
                "jobId": job["jobId"],
                "status": "COMPLETED",
                "processAlive": False,
                "reference": reference if job["mode"] == "BUILD_REFERENCE" else None,
                "observations": observations,
                **changes,
            }
        ],
    )


def test_first_reference_then_second_device_reproduces_it(v3_study):
    lab, d, auth, model = setup(v3_study)
    c, store, runtime, admin = lab
    job = start(lab, d, model)
    assert job["mode"] == "BUILD_REFERENCE"
    command = next(x for x in runtime.commands(d["deviceId"]) if x["kind"] == "QUALIFY_MODEL")
    assert command["manifest"] == model["manifest"] and command["reference"] is None
    assert model["manifestHash"] not in runtime.devices()[0]["selfTest"]["qualifiedModelHashes"]
    dataset = c.get("/api/v1/datasets", headers=admin).json()[0]
    draft = configuration(d, model, dataset)
    assert c.post("/api/v1/experiments", headers=admin, json=draft).status_code == 422
    result = finish(c, auth, job, model)
    assert job["jobId"] in result["acceptedQualifications"]
    shown = c.get(route(model), headers=admin).json()
    assert shown["jobs"][0]["status"] == "COMPLETED"
    assert shown["referenceHash"] == canonical_json_hash(report_inputs(model)[0])
    assert model["manifestHash"] in runtime.devices()[0]["selfTest"]["qualifiedModelHashes"]
    with store.db() as db:
        raw = json.loads(db.execute("SELECT self_test FROM devices WHERE id=?", (d["deviceId"],)).fetchone()[0])
    assert raw["qualifiedModelHashes"] == ["f" * 64]
    assert c.post("/api/v1/experiments", headers=admin, json=draft).status_code == 200
    # A second device receives the frozen reference, including every executable input.
    _, d2, auth2, _ = setup(v3_study, "second-gpu")
    second = start(lab, d2, model)
    assert second["mode"] == "COMPARE_REFERENCE"
    command = next(x for x in runtime.commands(d2["deviceId"]) if x["kind"] == "QUALIFY_MODEL")
    assert command["reference"] == report_inputs(model)[0]
    finish(c, auth2, second, model)
    assert all(model["manifestHash"] in x["selfTest"]["qualifiedModelHashes"] for x in runtime.devices())


@pytest.mark.parametrize("alive", [None, True])
def test_completion_does_not_release_an_unknown_or_living_process(v3_study, alive):
    lab, d, auth, model = setup(v3_study)
    c, store, runtime, admin = lab
    job = start(lab, d, model)
    finish(c, auth, job, model, processAlive=alive)
    rid = queued(lab, d)
    store.dispatch_once()
    assert store.get(rid)["status"] == "QUEUED"
    assert model["manifestHash"] not in runtime.devices()[0]["selfTest"]["qualifiedModelHashes"]
    with store.db() as db:
        db.execute("UPDATE devices SET seen=0")
    store.dispatch_once()
    assert c.post(route(model), headers=admin, json={"deviceId": d["deviceId"]}).status_code == 409
    finish(c, auth, job, model)
    store.dispatch_once()
    assert store.get(rid)["status"] == "STARTING"


@pytest.mark.parametrize("damage", ["repeat", "restore", "config", "manifest", "negative"])
def test_lab_independently_rejects_corrupted_reports(v3_study, damage):
    lab, d, auth, model = setup(v3_study)
    c, _, runtime, admin = lab
    job = start(lab, d, model)
    reference, observations = report_inputs(model)
    if damage == "repeat":
        observations["1"][1]["outputsHash"] = "0" * 64
    if damage == "restore":
        observations["-1"][0]["restoredSha256"] = "0" * 64
    if damage == "config":
        reference["cell"]["config"]["maxNewTokens"] = 4096
    if damage == "manifest":
        reference["manifestHash"] = "0" * 64
    if damage == "negative":
        observations.pop("-1")
    finish(c, auth, job, model, reference=reference, observations=observations)
    shown = c.get(route(model), headers=admin).json()
    assert shown["jobs"][0]["status"] == "FAILED" and shown["referenceHash"] is None
    assert model["manifestHash"] not in runtime.devices()[0]["selfTest"]["qualifiedModelHashes"]
    if damage == "restore":
        assert runtime.devices()[0]["approvalStatus"] == "QUARANTINED"


def test_restore_failure_from_the_child_quarantines_the_device(v3_study):
    lab, d, auth, model = setup(v3_study)
    c, _, runtime, _ = lab
    job = start(lab, d, model)
    finish(c, auth, job, model, status="FAILED", observations=None, reference=None, errorCode="RESTORE_MISMATCH")
    assert runtime.devices()[0]["approvalStatus"] == "QUARANTINED"


def test_cancel_is_fenced_and_other_devices_cannot_release_the_gpu(v3_study):
    lab, d, auth, model = setup(v3_study)
    c, _, runtime, admin = lab
    _, other, other_auth, _ = setup(v3_study, "other-gpu")
    job = start(lab, d, model)
    finish(c, other_auth, job, model)
    assert c.post(route(model), headers=admin, json={"deviceId": other["deviceId"]}).status_code == 409
    assert c.post(route(model) + "/" + job["jobId"] + "/cancel", headers=admin).status_code == 200
    assert any(x["kind"] == "CANCEL_MODEL_QUALIFICATION" for x in runtime.commands(d["deviceId"]))
    finish(c, auth, job, model)
    shown = c.get(route(model), headers=admin).json()
    assert shown["jobs"][0]["status"] == "CANCELLED" and shown["referenceHash"] is None


def test_qualification_invalidates_when_the_native_profile_changes(v3_study):
    lab, d, auth, model = setup(v3_study)
    c, store, runtime, _ = lab
    finish(c, auth, start(lab, d, model), model)
    with store.db() as db:
        row = db.execute("SELECT self_test FROM devices WHERE id=?", (d["deviceId"],)).fetchone()
        profile = json.loads(row[0])
        profile["environment"]["driver"] = "changed"
        db.execute("UPDATE devices SET self_test=? WHERE id=?", (json.dumps(profile), d["deviceId"]))
    assert model["manifestHash"] not in runtime.devices()[0]["selfTest"]["qualifiedModelHashes"]


def test_probe_requires_current_capabilities_workspace_and_contribution(v3_study):
    lab, d, auth, model = setup(v3_study)
    c, store, _, admin = lab
    assert c.post(route(model), json={"deviceId": d["deviceId"]}).status_code == 401
    assert (
        c.post(
            route(model), headers={**admin, "X-Workspace-Id": "elsewhere"}, json={"deviceId": d["deviceId"]}
        ).status_code
        == 403
    )
    with store.db() as db:
        db.execute("UPDATE devices SET desired=0")
    assert c.post(route(model), headers=admin, json={"deviceId": d["deviceId"]}).status_code == 409
    enable(lab, d, {"Authorization": auth["Authorization"]})
    assert c.post(route(model), headers=admin, json={"deviceId": d["deviceId"]}).status_code == 409


def test_upload_grants_are_limited_to_the_active_probe_and_exact_manifest(v3_study):
    lab, d, auth, model = setup(v3_study)
    c, store, _, admin = lab
    model.update(source="UPLOAD", status="READY")
    with store.db() as db:
        db.execute("UPDATE study_assets SET body=? WHERE id=?", (json.dumps(model), model["id"]))
    job = start(lab, d, model)
    sha = model["manifest"]["files"]["config.json"]
    query = {"jobId": job["jobId"], "sha256": sha}
    assert c.post("/api/v1/device/model-transfer", headers=auth, json=query).status_code == 200
    assert c.post("/api/v1/device/model-transfer", headers=auth, json={**query, "sha256": "0" * 64}).status_code == 403
    assert c.post(route(model) + "/" + job["jobId"] + "/cancel", headers=admin).status_code == 200
    assert c.post("/api/v1/device/model-transfer", headers=auth, json=query).status_code == 403
    finish(c, auth, job, model)
    assert c.post("/api/v1/device/model-transfer", headers=auth, json=query).status_code == 403


def test_stopped_contribution_cannot_change_endpoints_while_the_probe_is_still_unknown(v3_study):
    lab, d, auth, model = setup(v3_study)
    c, _, _, admin = lab
    start(lab, d, model)
    assert (
        c.post(
            "/api/v1/devices/" + d["deviceId"] + "/contribution",
            headers=admin,
            json={"enabled": False, "bootId": "boot-1"},
        ).status_code
        == 200
    )
    boot(c, auth, "boot-1", contribution=False)
    assert (
        c.patch(
            "/api/v1/devices/" + d["deviceId"] + "/endpoints",
            headers=admin,
            json={"computeUrl": "http://127.0.0.1:18888"},
        ).status_code
        == 409
    )
