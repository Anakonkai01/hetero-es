"""A notebook submits through the real lab routes: a hub-pinned model, rows from its own loader, a cell-written reward
and sampler; no GPU and no numerical imports."""

import linecache
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from test_cpu_coordinator import enroll_cpu
from test_lab_cli import specification
from test_v3_study import qualify_v3, v3_study as study_fixture
from labkit import pair, enable


@pytest.fixture
def v3_study(tmp_path):
    yield from study_fixture.__wrapped__(tmp_path)


def cell(source, name):
    filename = f"<ipython-input-{abs(hash(source))}>"
    linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
    namespace = {"__name__": "__main__"}
    exec(compile(source, filename, "exec"), namespace)
    return namespace[name]


REWARD = "def match(completions, rows):\n    return [float(t == r['label']) for t, r in zip(completions, rows)]\n"
SAMPLER = "def first(generation, size, train_rows, seed):\n    return [(generation * size + i) % train_rows for i in range(size)]\n"


def notebook_lab(client, headers):
    from heteroes.sdk_lab import Lab, LabError

    class TestLab(Lab):
        def request(self, method, path, body=None, **_):
            response = client.request(method, path, headers=headers, json=body)
            if response.status_code >= 400:
                raise LabError(f"Lab HTTP {response.status_code}: {response.json().get('detail')}")
            return response.json()

        def upload(self, plan, path):
            response = client.put(urlsplit(plan["url"]).path, content=Path(path).read_bytes(), headers=plan["headers"])
            assert response.status_code in (200, 201, 204), response.text

    return TestLab("https://lab.example", "token", "lab")


def test_a_notebook_submits_a_hub_model_its_own_rows_reward_and_sampler(v3_study, tmp_path, monkeypatch):
    from heteroes.canonical import canonical_json_hash
    from heteroes.sdk import ESConfig, ESTrainer
    from heteroes.sdk_lab import Dataset, Model
    from heteroes.v3.model import registration_manifest

    client, admin, _ = v3_study
    store = client.app.state.store
    lab_kit = client, store, store.runtime, admin
    cpu, cpu_auth = enroll_cpu(lab_kit)
    gpu, gpu_auth = pair(lab_kit, "gpu")
    path = specification(tmp_path)["model"]["path"]
    manifest = registration_manifest(path, "org/hub-model", "b" * 40)
    model = Model("org/hub-model", path, "b" * 40, "REFERENCE", manifest)
    profile = next(d["selfTest"] for d in store.runtime.devices() if d["deviceId"] == gpu["deviceId"])
    qualify_v3(client, gpu_auth, profile, {"manifestHash": canonical_json_hash(manifest)})
    enable(lab_kit, cpu, cpu_auth)
    enable(lab_kit, gpu, gpu_auth)
    lab = notebook_lab(client, admin)
    assert {d.worker_id for d in lab.devices()} >= {"gpu"}
    # an uploaded copy of the same files exists: it needs the private route, so a hub reference is registered beside it
    uploaded = lab.request("POST", "/api/v1/models/register", {"recipeVersion": 3, "name": "copy", "manifest": manifest, "source": "UPLOAD"})  # fmt: skip
    sizes = {name: (Path(path) / name).stat().st_size for name in manifest["files"]}
    for name, plan in lab.request("POST", f"/api/v1/models/{uploaded['id']}/upload-plan", sizes).items():
        lab.upload(plan, Path(path) / name)
    assert lab.request("POST", f"/api/v1/models/{uploaded['id']}/publish")["status"] == "READY"
    asked = []
    lab.qualify = lambda m, devices, log, engine, decoder=None: asked.append((m, [d.worker_id for d in devices]))

    rows = [{"prompt": f"Q{i}", "label": "A"} for i in range(20)]
    data = Dataset.from_rows(train=rows[:12], validation=rows[12:16], test=rows[16:], directory=tmp_path / "rows")
    args = ESConfig(model=model, dataset=data, population=4, generations=2, batch_size=4, eval_chunk=16,
                    eval_chunks=[16, 32], validation_interval=1)  # fmt: skip
    trainer = ESTrainer(args, reward_func=cell(REWARD, "match"), sampler_func=cell(SAMPLER, "first"),
                        code_dir=tmp_path / "code")  # fmt: skip
    monkeypatch.chdir(tmp_path)
    run = trainer.submit(lab, coordinator=cpu["deviceId"], workers=["gpu"], name="notebook run", log=lambda *_: None)
    body = client.get(f"/api/v1/experiments/{run.id}", headers=admin).json()
    assert body["status"] == "QUEUED" and body["name"] == "notebook run"
    assert body["modelSource"] == "REFERENCE"  # every device downloads it from the hub: no private route needed
    roles = {entry["role"]: entry for entry in body["pythonCode"]}
    assert set(roles) == {"scorer", "sampler"} and roles["sampler"]["source"] == SAMPLER
    assert body["sampler"] == "python@1:" + roles["sampler"]["codeSha256"]
    assert (body["evalChunk"], body["evalChunks"], body["validationInterval"]) == (16, [16, 32], 1)
    models = client.get("/api/v1/models", headers=admin).json()
    assert sorted(m["source"] for m in models if m.get("manifestHash") == model.manifest_hash) == [
        "REFERENCE",
        "UPLOAD",
    ]
    assert asked == [(model, [cpu["workerId"], "gpu"])]  # the coordinator and every worker, before the experiment
    # the devices the run needs are already qualified: nothing is asked of them again
    del lab.qualify
    lab.qualify(model, ["gpu"], log=lambda *_: pytest.fail("no qualification expected"))
