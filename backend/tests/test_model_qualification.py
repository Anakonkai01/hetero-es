"""A model probe owns its GPU until confirmed death; the CPU lab checks every signed repeat itself."""

from copy import deepcopy
import json

import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.noise.contracts import ENGINE_V2, ENGINE_VERSION
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


def report_inputs(model, engine=ENGINE_V2, decoder="hf_generate"):
    """Synthetic observations exercise admission, not GPU numerical compatibility."""
    manifest = model["manifest"]
    recipe, plan = _documents(manifest, "a" * 64, "b" * 64, engine, decoder)
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
            "config": cell_configs(
                manifest["modelId"], manifest["revision"], None if engine == ENGINE_VERSION else engine, decoder
            )["full"],
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
    response = c.post(
        route(model), headers=admin, json={"deviceId": device["deviceId"], "noiseEngineVersion": ENGINE_V2}
    )
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
    assert shown["referenceHashesByNoiseEngine"][ENGINE_V2] == canonical_json_hash(report_inputs(model)[0])
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
    assert (
        c.post(
            route(model), headers=admin, json={"deviceId": other["deviceId"], "noiseEngineVersion": ENGINE_V2}
        ).status_code
        == 409
    )
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


MEMORY = {
    "formatVersion": 1,
    "promptTokens": 200,
    "newTokens": 256,
    "baseBytes": 3_000_000_000,
    "totalBytes": 16_000_000_000,
    "chunks": [
        {"chunk": 16, "ran": True, "peakBytes": 4_000_000_000, "seconds": 9.5},
        {"chunk": 32, "ran": True, "peakBytes": 5_000_000_000, "seconds": 11.0},
        {"chunk": 64, "ran": False, "peakBytes": None, "seconds": None},
    ],
}


def test_a_qualification_keeps_what_the_gpu_measured_per_chunk_and_drops_anything_else(v3_study):
    # owner 2026-10-22: a batch and chunks are suggested from each GPU's own numbers, also for a GPU never seen before
    lab, d, auth, model = setup(v3_study)
    c, _, _, admin = lab
    job = start(lab, d, model)
    finish(c, auth, job, model, chunkMemory=MEMORY)
    assert c.get(route(model), headers=admin).json()["jobs"][0]["chunkMemory"] == MEMORY
    _, d2, auth2, _ = setup(v3_study, "second-gpu")
    second = start(lab, d2, model)
    finish(c, auth2, second, model, chunkMemory={**MEMORY, "secret": "x"})
    jobs = c.get(route(model), headers=admin).json()["jobs"]
    assert jobs[0]["status"] == "COMPLETED" and jobs[0]["chunkMemory"] is None  # the qualification still stands


def test_old_and_new_references_coexist_without_cross_engine_admission(v3_study):
    lab, device, auth, model = setup(v3_study)
    c, store, runtime, admin = lab
    old = c.post(
        route(model), headers=admin, json={"deviceId": device["deviceId"], "noiseEngineVersion": ENGINE_VERSION}
    )
    assert old.status_code == 201, old.text
    reference, observations = report_inputs(model, ENGINE_VERSION)
    finish(c, auth, old.json(), model, reference=reference, observations=observations)
    with store.db() as db:
        row = db.execute("SELECT * FROM model_references").fetchone()
        old_bytes = tuple(row)
    from backend.policies import v3_qualification

    profile = runtime.devices()[0]["selfTest"]
    assert v3_qualification(profile, model["manifestHash"], ENGINE_VERSION) is None
    assert v3_qualification(profile, model["manifestHash"], ENGINE_V2) == "model"
    new = start(lab, device, model)
    assert new["mode"] == "BUILD_REFERENCE"
    finish(c, auth, new, model)
    profile = runtime.devices()[0]["selfTest"]
    for engine in (ENGINE_VERSION, ENGINE_V2):
        assert v3_qualification(profile, model["manifestHash"], engine) is None
    with store.db() as db:
        assert tuple(db.execute("SELECT * FROM model_references").fetchone()) == old_bytes
        assert db.execute("SELECT count(*) FROM model_engine_references").fetchone()[0] == 1


def test_new_engine_probe_rejects_a_valid_old_engine_reference(v3_study):
    lab, device, auth, model = setup(v3_study)
    c, _, runtime, admin = lab
    job = start(lab, device, model)
    reference, observations = report_inputs(model, ENGINE_VERSION)
    finish(c, auth, job, model, reference=reference, observations=observations)
    assert c.get(route(model), headers=admin).json()["jobs"][0]["errorCode"] == "MODEL_QUALIFICATION_MISMATCH"
    assert model["manifestHash"] not in runtime.devices()[0]["selfTest"]["qualifiedModelHashes"]


# ---- M4: strict_b22_v1 has its own reference and qualification, keyed by engine and decoder ------------------------

STRICT = "strict_b22_v1"


def start_strict(lab, device, model):
    c, _, _, admin = lab
    body = {"deviceId": device["deviceId"], "noiseEngineVersion": ENGINE_V2, "decoder": STRICT}
    response = c.post(route(model), headers=admin, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_strict_qualification_is_separate_from_the_plain_one(v3_study):
    from backend.policies import v3_qualification

    lab, device, auth, model = setup(v3_study)
    c, store, runtime, admin = lab
    finish(c, auth, start(lab, device, model), model)  # plain engine v2 qualification
    profile = runtime.devices()[0]["selfTest"]
    assert v3_qualification(profile, model["manifestHash"], ENGINE_V2) is None
    assert v3_qualification(profile, model["manifestHash"], ENGINE_V2, STRICT) == "model"
    job = start_strict(lab, device, model)
    assert job["mode"] == "BUILD_REFERENCE" and job["decoder"] == STRICT
    command = next(x for x in runtime.commands(device["deviceId"]) if x.get("jobId") == job["jobId"])
    assert command["decoder"] == STRICT and command["noiseEngineVersion"] == ENGINE_V2
    reference, observations = report_inputs(model, ENGINE_V2, STRICT)
    finish(c, auth, job, model, reference=reference, observations=observations)
    profile = runtime.devices()[0]["selfTest"]
    assert v3_qualification(profile, model["manifestHash"], ENGINE_V2, STRICT) is None
    assert v3_qualification(profile, model["manifestHash"], ENGINE_V2) is None
    status = c.get(route(model), headers=admin).json()
    assert set(status["referenceHashesByNoiseEngine"]) == {ENGINE_V2, f"{ENGINE_V2}+{STRICT}"}


def test_a_strict_probe_rejects_a_plain_reference(v3_study):
    lab, device, auth, model = setup(v3_study)
    c, _, runtime, admin = lab
    job = start_strict(lab, device, model)
    reference, observations = report_inputs(model, ENGINE_V2)  # valid, but for hf_generate
    finish(c, auth, job, model, reference=reference, observations=observations)
    assert c.get(route(model), headers=admin).json()["jobs"][0]["errorCode"] == "MODEL_QUALIFICATION_MISMATCH"
    from backend.policies import v3_qualification

    assert v3_qualification(runtime.devices()[0]["selfTest"], model["manifestHash"], ENGINE_V2, STRICT) == "model"


def test_a_plain_probe_rejects_a_strict_reference(v3_study):
    lab, device, auth, model = setup(v3_study)
    c, _, _, admin = lab
    job = start(lab, device, model)
    reference, observations = report_inputs(model, ENGINE_V2, STRICT)
    finish(c, auth, job, model, reference=reference, observations=observations)
    assert c.get(route(model), headers=admin).json()["jobs"][0]["errorCode"] == "MODEL_QUALIFICATION_MISMATCH"


def test_an_unknown_probe_decoder_is_refused(v3_study):
    lab, device, _, model = setup(v3_study)
    c, _, _, admin = lab
    body = {"deviceId": device["deviceId"], "noiseEngineVersion": ENGINE_V2, "decoder": "hf_compact"}
    assert c.post(route(model), headers=admin, json=body).status_code == 422


def test_a_strict_experiment_needs_the_strict_qualification_of_every_device(v3_study):
    lab, first, first_auth, model = setup(v3_study, "strict-a")
    second_lab, second, second_auth, _ = setup(v3_study, "strict-b")
    c, store, runtime, admin = lab
    reference, observations = report_inputs(model, ENGINE_V2, STRICT)
    for each_lab, device, auth in ((lab, first, first_auth), (second_lab, second, second_auth)):
        finish(c, auth, start(each_lab, device, model), model)
    finish(c, first_auth, start_strict(lab, first, model), model, reference=reference, observations=observations)
    body = strict_body(lab, first, [second], model)  # the worker has the plain qualification only
    refused = c.post("/api/v1/experiments", headers=admin, json=body)
    assert refused.status_code == 422 and "with the strict decoder" in refused.text, refused.text
    reference, observations = report_inputs(model, ENGINE_V2, STRICT)
    finish(
        c, second_auth, start_strict(second_lab, second, model), model, reference=reference, observations=observations
    )
    created = c.post("/api/v1/experiments", headers=admin, json=body)
    assert created.status_code == 200, created.text
    shown = created.json()
    assert shown["decodeEngine"] == STRICT and shown["evalDtype"] == "float16" and shown["evalChunk"] == 32
    fp32 = c.post("/api/v1/experiments", headers=admin, json={**body, "evalDtype": "float32"})
    assert fp32.status_code == 422  # the strict decoder reads the live FP16 weights
    plain = c.post("/api/v1/experiments", headers=admin, json={**body, "decodeEngine": "hf_generate"})
    assert plain.status_code == 422 and "only for the strict decoder" in plain.text


def test_a_pending_probe_blocks_only_probes_of_the_same_reference(v3_study):
    first_lab, first, _, model = setup(v3_study, "probe-gpu")
    second_lab, second, _, _ = setup(v3_study, "probe-gpu-2")
    third_lab, third, _, _ = setup(v3_study, "probe-gpu-3")
    c, _, _, admin = first_lab
    start_strict(first_lab, first, model)  # the strict reference is pending: no reference exists yet
    assert start(second_lab, second, model)["mode"] == "BUILD_REFERENCE"  # another reference: not blocked
    for decoder in (STRICT, "hf_generate"):  # each reference waits for its own first device
        body = {"deviceId": third["deviceId"], "noiseEngineVersion": ENGINE_V2, "decoder": decoder}
        assert c.post(route(model), headers=admin, json=body).status_code == 409


def test_a_profile_without_per_engine_hashes_never_qualifies_for_the_strict_decoder():
    from backend.policies import v3_qualification

    legacy = {"recipeVersions": [3], "noiseVersion": ENGINE_V2, "qualifiedModelHashes": ["a" * 64]}
    assert v3_qualification(legacy, "a" * 64, ENGINE_V2) is None
    assert v3_qualification(legacy, "a" * 64, ENGINE_V2, STRICT) == "model"


def test_a_plain_experiment_keeps_its_document_and_a_strict_one_submits_fp16(v3_study):
    lab, first, second, model = strict_pair(v3_study)
    c, store, runtime, admin = lab
    plain = {**strict_body(lab, first, [first], model), "decodeEngine": "hf_generate", "evalDtype": None}
    plain = c.post("/api/v1/experiments", headers=admin, json=plain)
    assert plain.status_code == 200, plain.text
    assert "evalDtype" not in plain.json()  # earlier managed runs carry no such field
    strict = c.post("/api/v1/experiments", headers=admin, json=strict_body(lab, first, [second], model)).json()
    submitted = []
    real = runtime.submit
    runtime.submit = lambda config: (submitted.append(config), real(config))[1]
    assert c.post(f"/api/v1/experiments/{strict['experimentId']}/submit", headers=admin).status_code == 200
    store.dispatch_once()
    assert submitted and submitted[0]["decodeEngine"] == STRICT and submitted[0]["evalDtype"] == "float16", submitted


# ---- M4 D1: one weight set per GPU in a strict run (ADR-013) --------------------------------------------------------


def strict_pair(study):
    """Two GPU devices of one lab, each qualified for the pinned model with the plain and the strict decoder."""
    first_lab, first, first_auth, model = setup(study, "strict-a")
    second_lab, second, second_auth, _ = setup(study, "strict-b")
    for lab, device, auth in ((first_lab, first, first_auth), (second_lab, second, second_auth)):
        c, _, _, _ = lab
        finish(c, auth, start(lab, device, model), model)
        reference, observations = report_inputs(model, ENGINE_V2, STRICT)
        finish(c, auth, start_strict(lab, device, model), model, reference=reference, observations=observations)
    return first_lab, first, second, model


def strict_body(lab, coordinator, workers, model):
    from test_v3_study import configuration

    c, _, runtime, admin = lab
    data = next(d for d in c.get("/api/v1/datasets", headers=admin).json() if d.get("recipeVersion") == 3)
    paired = next(d for d in runtime.devices() if d["deviceId"] == coordinator["deviceId"])
    body = {**configuration(paired, model, data), "noiseEngineVersion": ENGINE_V2, "evalChunk": 32}
    return {**body, "workerIds": [w["workerId"] for w in workers], "decodeEngine": STRICT, "evalDtype": "float16"}


def test_a_strict_run_never_shares_its_coordinators_gpu_with_a_worker(v3_study):
    lab, first, second, model = strict_pair(v3_study)
    c, store, runtime, admin = lab
    shared = c.post("/api/v1/experiments", headers=admin, json=strict_body(lab, first, [first, second], model))
    assert shared.status_code == 422 and "one weight set per GPU" in shared.text, shared.text
    plain = {**strict_body(lab, first, [first], model), "decodeEngine": "hf_generate", "evalDtype": None}
    assert c.post("/api/v1/experiments", headers=admin, json=plain).status_code == 200  # earlier recipes unchanged
    created = c.post("/api/v1/experiments", headers=admin, json=strict_body(lab, first, [second], model))
    assert created.status_code == 200, created.text
    run = created.json()["experimentId"]
    assert c.post(f"/api/v1/experiments/{run}/submit", headers=admin).status_code == 200
    store.dispatch_once()
    assert store.get(run)["status"] == "STARTING", store.get(run).get("waitingReason")
    [assignment] = [r for r in runtime.runs() if r["runId"] == run]
    with store.db() as db:
        _, assignment = runtime._assignment(db, assignment["assignmentId"])
        # a worker joining later passes the same rule (ADR-009 joins use waiting_reason with the joining worker)
        reason = runtime.waiting_reason(store.get(run), db, [first["workerId"]])
        assert reason and "one weight set per GPU" in reason
        assert runtime.waiting_reason(store.get(run), db, [second["workerId"]]) is None
    assert assignment["workerDevices"] == {second["workerId"]: second["deviceId"]}


def test_a_strict_run_needs_a_gpu_coordinator(v3_study):
    from test_cpu_coordinator import enroll_cpu

    lab, first, second, model = strict_pair(v3_study)
    c, _, runtime, admin = lab
    cpu, _ = enroll_cpu(lab)
    body = {**strict_body(lab, first, [first, second], model), "coordinatorDeviceId": cpu["deviceId"]}
    refused = c.post("/api/v1/experiments", headers=admin, json=body)
    assert refused.status_code == 422 and "GPU coordinator" in refused.text, refused.text
    workers = body["workerIds"]
    assert runtime.waiting_reason(body, workers=workers) and "GPU coordinator" in runtime.waiting_reason(
        body, workers=workers
    )


def test_the_strict_layout_compares_devices_and_physical_gpus():
    from backend.policies import strict_layout

    body = {"decodeEngine": STRICT}
    gpu = {"runtimeProfile": "native-gpu"}
    coordinator = {"deviceId": "a", "physicalResourceId": None, "selfTest": gpu}
    assert "one weight set" in strict_layout(body, coordinator, [{"deviceId": "a", "physicalResourceId": None}])
    coordinator = {**coordinator, "physicalResourceId": "gpu-1"}
    alias = {"deviceId": "b", "physicalResourceId": "gpu-1"}  # another enrollment of the same physical GPU
    assert "one weight set" in strict_layout(body, coordinator, [alias])
    assert strict_layout(body, coordinator, [{"deviceId": "b", "physicalResourceId": "gpu-2"}]) is None
    assert strict_layout(body, {**coordinator, "physicalResourceId": None}, [alias]) is None
    assert strict_layout({"decodeEngine": "hf_generate"}, coordinator, [alias]) is None
