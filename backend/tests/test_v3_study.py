"""v3 assets, declarative configuration and qualification fences use no torch or NumPy."""

import json

import pytest

from test_study import study as study_fixture, manifest
from test_devices import pair, enable


@pytest.fixture
def v3_study(tmp_path):
    yield from study_fixture.__wrapped__(tmp_path)


def assets(study):
    c, admin, storage = study
    model_manifest, _ = manifest()
    model_manifest["modelId"] = "research/custom-causal-lm"
    model_manifest["revision"] = model_manifest["tokenizerRevision"] = "e" * 40
    response = c.post(
        "/api/v1/models/register",
        headers=admin,
        json={
            "recipeVersion": 3,
            "name": "Custom model",
            "manifest": model_manifest,
        },
    )
    assert response.status_code == 201, response.text
    model = response.json()
    imported = c.post(
        "/api/v1/datasets/import",
        headers=admin,
        json={
            "recipeVersion": 3,
            "name": "Arbitrary columns",
            "mapping": {"prompt": "question"},
            "files": {
                "all": {
                    "format": "json",
                    "content": json.dumps(
                        [{"question": f"Question {i}", "label": "A", "level": i, "optional": None} for i in range(20)]
                    ),
                }
            },
        },
    )
    assert imported.status_code == 201, imported.text
    return model, imported.json()


def qualify_v3(c, device_auth, profile, model):
    profile.update(recipeVersions=[3], qualifiedModelHashes=[model["manifestHash"]])
    profile["compatibility"]["recipeV3"] = {
        "passed": True,
        "repeatIdentical": True,
        "modelManifestHash": model["manifestHash"],
        "recipeHash": "a" * 64,
        "parentSha256": "b" * 64,
        "restoredSha256": "b" * 64,
        "perturbedSha256": "c" * 64,
        "outputsHash": "d" * 64,
    }
    result = c.patch(
        "/api/v1/device/qualification", headers=device_auth, json={"bootId": "boot-1", "selfTest": profile}
    )
    assert result.status_code == 200, result.text


def configuration(d, model, data):
    return {
        "name": "V3 custom run",
        "recipeVersion": 3,
        "modelName": model["reference"],
        "modelArtifactId": model["id"],
        "workerIds": [d["workerId"]],
        "coordinatorDeviceId": d["deviceId"],
        "datasetIds": [data["datasetId"]],
        "task": "text_v3",
        "batchSize": 4,
        "antithetic": True,
        "coefficientRule": "zscore@1",
        "systemPrompt": None,
        "weightSpace": {"kind": "subset", "include": [r"layers\.1\."]},
        "scorer": {
            "kind": "declarative",
            "name": "choice-letter",
            "version": 1,
            "codeSha256": None,
            "config": {"answerField": "label"},
        },
    }


def test_v3_import_keeps_columns_and_rejects_leakage(v3_study):
    from heteroes.v3.data import verify

    c, admin, storage = v3_study
    model, imported = assets(v3_study)
    raw = json.loads(b"".join(storage.get("objects/" + imported["objectSha256"])))
    verify(raw)
    assert imported["recipeVersion"] == 3
    assert set(raw["splits"]["train"][0]) == {"prompt", "question", "label", "level", "optional"}
    response = c.post(
        "/api/v1/datasets/import",
        headers=admin,
        json={
            "recipeVersion": 3,
            "name": "bad",
            "files": {"all": {"format": "json", "content": json.dumps([{"prompt": "duplicate"}] * 20)}},
        },
    )
    assert response.status_code == 422


def test_v3_config_and_worker_command_preserve_the_frozen_options(v3_study):
    c, admin, _ = v3_study
    store = c.app.state.store
    lab = (c, store, store.runtime, admin)
    d, device_auth = pair(lab)
    model, data = assets(v3_study)
    body = configuration(d, model, data)
    assert c.post("/api/v1/experiments", headers=admin, json=body).status_code == 422
    profile = c.get("/api/v1/devices", headers=admin).json()[0]["selfTest"]
    qualify_v3(c, device_auth, profile, model)
    result = c.post("/api/v1/experiments", headers=admin, json=body)
    assert result.status_code == 200, result.text
    run = result.json()
    assert run["modelVersion"] == model["revision"]
    enable(lab, d, device_auth)
    assert c.post(f"/api/v1/experiments/{run['experimentId']}/submit", headers=admin).status_code == 200
    store.dispatch_once()
    ar = store.runtime.runs()[0]
    with store.db() as db:
        _, assignment = store.runtime._assignment(db, ar["assignmentId"])
    for key in ("recipeVersion", "weightSpace", "antithetic", "scorer", "coefficientRule", "systemPrompt"):
        assert assignment["config"][key] == body[key]
    assert assignment["config"]["datasetIdentity"] == data["identity"]
    result = c.post(
        "/api/v1/device/worker-command",
        headers=device_auth,
        json={
            "assignmentId": ar["assignmentId"],
            "epoch": ar["epoch"],
            "workerId": d["workerId"],
            "action": "start",
        },
    )
    assert result.status_code == 200, result.text
    command = next(cmd for cmd in store.runtime.commands(d["deviceId"]) if cmd["kind"] == "START_WORKER")
    assert command["studyConfig"] == assignment["config"]

    query = {"assignmentId": ar["assignmentId"], "epoch": ar["epoch"], "sha256": data["objectSha256"]}
    assert c.post("/api/v1/device/study-transfer", headers=device_auth, json=query).status_code == 200
    assert c.post("/api/v1/device/study-transfer", headers=device_auth, json={**query, "epoch": 99}).status_code == 403
    from test_devices import boot

    metrics = {
        "best": {"validationReward": 0.75},
        "testLocked": False,
        "testReward": 0.5,
        "validation": [{"generation": 0, "meanReward": 0.75}],
    }
    boot(
        c,
        device_auth,
        "boot-1",
        contribution=True,
        reports=[
            {
                "assignmentId": ar["assignmentId"],
                "epoch": ar["epoch"],
                "sequence": 1,
                "snapshot": {
                    "state": {"status": "RUNNING"},
                    "generations": [],
                    "candidates": [],
                    "attempts": [],
                    "events": [],
                    "artifacts": [],
                    "studyMetrics": metrics,
                },
            }
        ],
    )
    store.dispatch_once()
    shown = c.get(f"/api/v1/experiments/{run['experimentId']}", headers=admin).json()
    assert shown["validationScore"] == 0.75 and shown["testScore"] == 0.5
    assert shown["studyMetrics"]["validation"] == metrics["validation"]


@pytest.mark.parametrize(
    "change",
    [
        {
            "scorer": {
                "kind": "python",
                "name": "code",
                "version": 1,
                "codeSha256": "a" * 64,
                "config": {"answerField": "label"},
            }
        },
        {"coefficientRule": "unknown@1"},
        {"antithetic": True, "candidatesPerGeneration": 3},
        {"weightSpace": {"kind": "subset", "include": ["["]}},
        {"weightSpace": {"kind": "lora", "rank": True, "alpha": 4, "targetModules": ["q_proj"]}},
        {
            "scorer": {
                "kind": "declarative",
                "name": "choice-letter",
                "version": 1,
                "codeSha256": None,
                "config": {"answerField": "absent"},
            }
        },
        {
            "scorer": {
                "kind": "declarative",
                "name": "countdown",
                "version": 1,
                "codeSha256": None,
                "config": {"numbersField": "label", "targetField": "absent"},
            }
        },
    ],
)
def test_v3_invalid_options_never_become_a_draft(v3_study, change):
    c, admin, _ = v3_study
    store = c.app.state.store
    d, device_auth = pair((c, store, store.runtime, admin))
    model, data = assets(v3_study)
    profile = c.get("/api/v1/devices", headers=admin).json()[0]["selfTest"]
    qualify_v3(c, device_auth, profile, model)
    response = c.post("/api/v1/experiments", headers=admin, json={**configuration(d, model, data), **change})
    assert response.status_code == 422, response.text


def test_v3_scorer_columns_are_every_field_of_its_config(v3_study):
    c, admin, _ = v3_study
    store = c.app.state.store
    d, device_auth = pair((c, store, store.runtime, admin))
    model, data = assets(v3_study)
    profile = c.get("/api/v1/devices", headers=admin).json()[0]["selfTest"]
    qualify_v3(c, device_auth, profile, model)
    scorer = {
        "kind": "declarative",
        "name": "countdown",
        "version": 1,
        "codeSha256": None,
        "config": {"numbersField": "question", "targetField": "level"},
    }
    response = c.post("/api/v1/experiments", headers=admin, json={**configuration(d, model, data), "scorer": scorer})
    assert response.status_code == 200, response.text


def test_v3_qualification_cannot_be_inferred_from_the_model_hash():
    from backend.policies import v3_qualification
    from backend.device_models import SelfTest
    from pydantic import ValidationError

    digest = "a" * 64
    assert v3_qualification({"recipeVersions": [1], "qualifiedModelHashes": [digest]}, digest) == "recipe"
    assert v3_qualification({"recipeVersions": [3], "qualifiedModelHashes": []}, digest) == "model"
    assert v3_qualification({"recipeVersions": [3], "qualifiedModelHashes": [digest]}, digest) is None
    with pytest.raises(ValidationError, match="compatibility"):
        SelfTest(
            passed=True,
            coordinator=True,
            gpuName="fixture",
            vramTotalMb=1024,
            noiseVersion="numpy_pcg64_normal_f32_to_f16_v1",
            recipeVersions=[3],
        )


def test_queued_v3_work_stops_when_a_device_loses_v3_qualification(v3_study):
    c, admin, _ = v3_study
    store = c.app.state.store
    d, device_auth = pair((c, store, store.runtime, admin))
    model, data = assets(v3_study)
    profile = c.get("/api/v1/devices", headers=admin).json()[0]["selfTest"]
    qualify_v3(c, device_auth, profile, model)
    run = c.post("/api/v1/experiments", headers=admin, json=configuration(d, model, data)).json()
    profile["recipeVersions"] = [1]
    assert (
        c.patch(
            "/api/v1/device/qualification", headers=device_auth, json={"bootId": "boot-1", "selfTest": profile}
        ).status_code
        == 200
    )
    assert store.runtime.waiting_reason(run) == "Recipe v3 qualification required"


def test_v3_templates_validate_and_keep_nullable_prompt():
    from backend.templates import clean_config
    from fastapi import HTTPException

    options = {
        "recipeVersion": 3,
        "weightSpace": {"kind": "full"},
        "antithetic": False,
        "systemPrompt": None,
        "coefficientRule": "zscore@1",
        "validationInterval": 2,
        "scorer": {
            "kind": "declarative",
            "name": "choice-letter",
            "version": 1,
            "codeSha256": None,
            "config": {"answerField": "label"},
        },
    }
    assert clean_config(options) == options
    with pytest.raises(HTTPException):
        clean_config({**options, "weightSpace": {"kind": "subset", "include": ["["]}})


def test_editing_a_v3_draft_replaces_its_old_recipe_fields(v3_study):
    c, admin, _ = v3_study
    store = c.app.state.store
    d, device_auth = pair((c, store, store.runtime, admin))
    model, data = assets(v3_study)
    profile = c.get("/api/v1/devices", headers=admin).json()[0]["selfTest"]
    qualify_v3(c, device_auth, profile, model)
    config = configuration(d, model, data)
    run = c.post("/api/v1/experiments", headers=admin, json=config).json()
    cap = c.get("/api/v1/capabilities", headers=admin).json()
    legacy = {
        key: value
        for key, value in config.items()
        if key not in ("weightSpace", "scorer", "antithetic", "systemPrompt", "coefficientRule", "datasetIds")
    }
    legacy.update(recipeVersion=1, task="arith16", modelArtifactId="qwen-pinned", modelName=cap["modelId"])
    result = c.patch(f"/api/v1/experiments/{run['experimentId']}", headers=admin, json=legacy)
    assert result.status_code == 200, result.text
    shown = result.json()
    assert shown.get("recipeVersion", 1) == 1
    assert shown["modelVersion"] == cap["modelRevision"]
    assert not set(shown) & {"weightSpace", "scorer", "antithetic", "modelManifest", "datasetIdentity"}


def test_only_current_v3_coordinator_can_quarantine_its_selected_worker(v3_study):
    import hashlib
    from test_devices import boot

    c, admin, _ = v3_study
    store = c.app.state.store
    lab = (c, store, store.runtime, admin)
    original, original_auth = pair(lab, "original")
    auditor, auditor_auth = pair(lab, "auditor", coordinator=False)
    outsider, _ = pair(lab, "outsider", coordinator=False)
    model, data = assets(v3_study)
    for device, auth in ((original, original_auth), (auditor, auditor_auth)):
        profile = next(
            d["selfTest"] for d in c.get("/api/v1/devices", headers=admin).json() if d["deviceId"] == device["deviceId"]
        )
        qualify_v3(c, auth, profile, model)
        enable(lab, device, auth)
    config = configuration(original, model, data)
    config["workerIds"].append(auditor["workerId"])
    run = c.post("/api/v1/experiments", headers=admin, json=config).json()
    c.post(f"/api/v1/experiments/{run['experimentId']}/submit", headers=admin)
    store.dispatch_once()
    ar = store.runtime.runs()[0]

    def report(auth, worker, epoch=1):
        event = {"event": "audit_worker_quarantined", "worker_id": worker, "reason": "AUDIT_MISMATCH", "t": 100}
        eid = hashlib.sha256(
            (ar["assignmentId"] + json.dumps(event, sort_keys=True, separators=(",", ":"))).encode()
        ).hexdigest()
        boot(
            c,
            auth,
            "boot-1",
            contribution=True,
            events=[{"eventId": eid, "assignmentId": ar["assignmentId"], "epoch": epoch, "event": event}],
        )

    def status(device):
        return next(d["approvalStatus"] for d in store.runtime.devices() if d["deviceId"] == device["deviceId"])

    report(auditor_auth, original["workerId"])
    report(original_auth, auditor["workerId"], epoch=99)
    report(original_auth, outsider["workerId"])
    assert status(original) == status(auditor) == status(outsider) == "APPROVED"
    report(original_auth, auditor["workerId"])
    assert status(auditor) == "QUARANTINED"
    report(original_auth, original["workerId"])
    assert status(original) == "QUARANTINED"
    assert status(outsider) == "APPROVED"

    # Replayed monitoring events must not undo a later administrator decision.
    with store.db() as db:
        db.execute("UPDATE devices SET status='APPROVED' WHERE id=?", (auditor["deviceId"],))
    report(original_auth, auditor["workerId"])
    assert status(auditor) == "APPROVED"
