"""The CLI offers pinned local inputs through the real managed-lab routes, without GPU/numerical imports."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from heteroes.canonical import canonical_json_hash
from test_cpu_coordinator import enroll_cpu
from test_v3_study import qualify_v3, v3_study as study_fixture
from labkit import pair, enable


@pytest.fixture
def v3_study(tmp_path):
    yield from study_fixture.__wrapped__(tmp_path)


class API:
    def __init__(self, client, headers):
        self.client, self.headers = client, headers

    def request(self, method, path, body=None):
        response = self.client.request(method, path, headers=self.headers, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"Lab HTTP {response.status_code}: {response.json().get('detail')}")
        return response.json()

    def upload(self, plan, path):
        response = self.client.put(urlsplit(plan["url"]).path, content=Path(path).read_bytes(), headers=plan["headers"])
        assert response.status_code in (200, 201, 204), response.text


def specification(tmp_path):
    from test_study import manifest

    _, files = manifest()
    model = tmp_path / "model"
    model.mkdir()
    for name, content in files.items():
        (model / name).write_bytes(content)
    rows = tmp_path / "data.jsonl"
    rows.write_text("".join(json.dumps({"question": f"Q{i}", "label": "A"}) + "\n" for i in range(20)))
    scorer = tmp_path / "reward.py"
    scorer.write_text(
        "def reward(completions, rows):\n    return [float(text == row['label']) for text, row in zip(completions, rows)]\n"
    )
    return {
        "model": {"path": str(model), "id": "research/custom-model", "revision": "a" * 40},
        "data": {"path": str(rows), "promptField": "question", "batchSize": 4, "sampler": "epoch-shuffle@1"},
        "population": 4,
        "generations": 2,
        "alpha": 0.001,
        "alphaSchedule": {"kind": "linear", "minimum": 0.0001},
        "momentum": {"beta": 0.875, "window": 3},
        "sigma": {"kind": "cosine", "initial": 0.01, "minimum": 0.001},
        "weightSpace": {"kind": "full"},
        "scorer": {"kind": "python", "name": "custom", "version": 1, "path": str(scorer), "function": "reward"},
        "coefficientRule": "centered-rank@1",
        "candidateSeedNamespace": "cli-lab-fixture",
        "evalChunk": 32,
        "validationInterval": 5,
        "allowJoin": True,
    }


def test_offer_uploads_pinned_inputs_freezes_code_and_is_idempotent(v3_study, tmp_path):
    from heteroes.v3.lab_cli import offer_experiment
    from heteroes.v3.model import registration_manifest

    client, admin, _ = v3_study
    store = client.app.state.store
    lab = client, store, store.runtime, admin
    cpu, cpu_auth = enroll_cpu(lab)
    gpu, gpu_auth = pair(lab, "gpu")
    spec = specification(tmp_path)
    manifest = registration_manifest(spec["model"]["path"], spec["model"]["id"], spec["model"]["revision"])
    profile = next(d["selfTest"] for d in store.runtime.devices() if d["deviceId"] == gpu["deviceId"])
    qualify_v3(client, gpu_auth, profile, {"manifestHash": canonical_json_hash(manifest)})
    enable(lab, cpu, cpu_auth)
    enable(lab, gpu, gpu_auth)
    api = API(client, admin)
    root = tmp_path / "offer"
    root.mkdir()
    result = offer_experiment(spec, cpu["deviceId"], ["gpu"], api, root)
    assert result["status"] == "DRAFT" and result["coordinatorDeviceId"] == cpu["deviceId"]
    assert result["sampler"] == "epoch-shuffle@1" and result["evalChunk"] == 32
    assert result["alphaSchedule"] == "linear" and result["momentumWindow"] == 3
    assert result["validationInterval"] == 5 and result["allowJoin"] is True
    assert result["pythonCode"][0]["source"] == Path(spec["scorer"]["path"]).read_text()
    assert result["scorer"]["codeSha256"] == result["pythonCode"][0]["codeSha256"]
    assert api.request("POST", f"/api/v1/experiments/{result['experimentId']}/submit")["status"] == "QUEUED"
    assert offer_experiment(spec, cpu["deviceId"], ["gpu"], api, root)["experimentId"] == result["experimentId"]
    assert len(api.request("GET", "/api/v1/experiments")) == 1
    receipt = (root / "lab-offer.json").read_text()
    assert "accessToken" not in receipt and "deviceToken" not in receipt
    # Changing a local file cannot silently reuse yesterday's frozen asset.
    Path(spec["data"]["path"]).write_text('{"question":"changed"}\n')
    with pytest.raises(ValueError, match="identity"):
        offer_experiment(spec, cpu["deviceId"], ["gpu"], api, root)


@pytest.mark.parametrize("field,value", [("evalDtype", "float16"), ("noiseEngine", "cuda")])
def test_lab_cli_does_not_silently_change_unsupported_recipe_choices(tmp_path, field, value):
    from heteroes.v3.lab_cli import managed_configuration, offer_experiment

    spec = specification(tmp_path)
    spec[field] = value
    with pytest.raises(ValueError):
        managed_configuration(spec, "co", ["gpu"], {"id": "model"}, {"datasetId": "data"})

    class NoWrite:
        def request(self, *args):
            raise AssertionError("Invalid settings must fail before uploading assets")

    with pytest.raises(ValueError):
        offer_experiment(spec, "co", ["gpu"], NoWrite(), tmp_path / "offer")
