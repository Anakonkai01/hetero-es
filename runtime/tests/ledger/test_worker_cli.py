"""The headless Linux Worker (`heteroes-worker`): pinned install, self-test, pairing and the agent configuration."""

import hashlib
import json
import os
import stat

import pytest

from heteroes.product import worker_cli
from heteroes.product.worker_cli import LabError, Worker, verified_download

SELF_TEST = {
    "passed": True,
    "coordinator": True,
    "gpuName": "NVIDIA GeForce RTX 3060",
    "vramTotalMb": 12288,
    "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
    "platform": "linux",
    "gpuUUID": "GPU-00000000-0000-0000-0000-000000000001",
    "recipeVersions": [3],
}


def item(tmp_path, name, data):
    source = tmp_path / "source" / name
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(data)
    return {"name": name, "url": source.as_uri(), "sha256": hashlib.sha256(data).hexdigest(), "sizeBytes": len(data)}


def bundle(tmp_path):
    root = tmp_path / "home"
    (root / "bundle").mkdir(parents=True)
    (root / "bundle" / "runtime.tar.gz").write_bytes(b"runtime")
    (root / "bundle" / "requirements-linux.txt").write_text("torch==2.13.0 --hash=sha256:00\n")
    profile = {
        "profile": "desktop-v3",
        "modelRevision": "rev1",
        "runtimeSha256": hashlib.sha256(b"runtime").hexdigest(),
        "modelFiles": [item(tmp_path, "model.safetensors", b"weights")],
        "platforms": {"linux": {"lockFile": "requirements-linux.txt", "wheels": [item(tmp_path, "t.whl", b"wheel")]}},
    }
    (root / "bundle" / "profile.json").write_text(json.dumps(profile))
    return Worker(root, say=lambda *_: None)


def test_a_download_is_kept_only_when_size_and_sha256_match(tmp_path):
    good = item(tmp_path, "a.bin", b"abc")

    assert verified_download(good, tmp_path / "out", lambda *_: None).read_bytes() == b"abc"
    with pytest.raises(RuntimeError, match="CHECKSUM_MISMATCH"):
        verified_download({**good, "name": "b.bin", "sha256": "0" * 64}, tmp_path / "out", lambda *_: None)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a.bin"]


def test_install_verifies_the_runtime_then_installs_the_lock_file_with_hashes_and_the_model(tmp_path):
    worker, calls = bundle(tmp_path), []

    worker.install(run=lambda argv, **kw: calls.append(argv))

    [pip] = calls
    assert pip[1:4] == ["-m", "pip", "install"] and "--no-index" in pip and "--require-hashes" in pip
    assert pip[-1].endswith("requirements-linux.txt")
    assert worker.installed()
    (worker.bundle / "runtime.tar.gz").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="RUNTIME_CHECKSUM_MISMATCH"):
        worker.install(run=lambda *a, **k: None)


def test_selftest_keeps_the_result_and_refuses_a_failed_admission(tmp_path):
    worker = bundle(tmp_path)
    worker.install(run=lambda *a, **k: None)

    class Done:
        def __init__(self, lines):
            self.stdout = "\n".join(json.dumps(line) for line in lines)

    worker.selftest(run=lambda *a, **k: Done([{"progress": {"stage": "model"}}, {"result": SELF_TEST}]))
    assert worker.settings()["selfTest"] == SELF_TEST
    with pytest.raises(RuntimeError, match="COMPATIBILITY_FAILED"):
        worker.selftest(run=lambda *a, **k: Done([{"error": "ValueError", "code": "COMPATIBILITY_FAILED"}]))
    with pytest.raises(RuntimeError, match="COMPATIBILITY_FAILED"):
        worker.selftest(run=lambda *a, **k: Done([{"result": {**SELF_TEST, "passed": False}}]))
    assert worker.settings()["selfTest"] == SELF_TEST


def paired(tmp_path, said=None):
    worker = bundle(tmp_path)
    worker.say = (said if said is not None else []).append
    worker.save_settings({"selfTest": SELF_TEST})
    requests = []

    def call(url, path, token, body, method=None):
        requests.append((path, body))
        if path == "/api/v1/health":
            return {"agentMode": True, "recipeVersions": [1, 2, 3]}
        return {
            "deviceId": "d" * 32,
            "workerId": body["workerId"],
            "deviceToken": "secret-token",
            "approvalStatus": "PENDING",
        }

    worker.join("https://lab.example/", "CODE-1", "3060 at home", call=call)
    return worker, requests


def test_join_enrolls_as_a_worker_only_device_and_keeps_the_token_out_of_settings_and_output(tmp_path):
    said = []
    worker, requests = paired(tmp_path, said)

    enrollment = requests[-1][1]
    assert enrollment["code"] == "CODE-1" and enrollment["workerId"].startswith("cli-")
    assert enrollment["computeUrl"] == "http://127.0.0.1:8765"
    assert enrollment["selfTest"] == {**SELF_TEST, "coordinator": False}  # offered only when asked for
    token = worker.paths()["token"]
    assert token.read_text() == "secret-token" and stat.S_IMODE(os.stat(token).st_mode) == 0o600
    assert "secret-token" not in json.dumps(worker.settings()) + " ".join(map(str, said))
    with pytest.raises(RuntimeError, match="ALREADY_PAIRED"):
        worker.join("https://lab.example", "CODE-2", "again", call=lambda *a, **k: {"agentMode": True})


def test_join_needs_a_passed_selftest_and_a_coordinator_needs_its_address(tmp_path):
    worker = bundle(tmp_path)
    with pytest.raises(RuntimeError, match="SELF_TEST_REQUIRED"):
        worker.join("https://lab.example", "C", "x", call=lambda *a, **k: {"agentMode": True})
    with pytest.raises(ValueError, match="--host"):
        worker.compute(coordinator=True)
    assert worker.compute(True, "100.92.20.58") == {"coordinator": True, "host": "100.92.20.58"}


def test_the_agent_configuration_matches_the_desktop_worker_and_carries_no_token(tmp_path):
    worker, _ = paired(tmp_path)

    config = json.loads(worker.agent_config().read_text())

    assert config["serverUrl"] == "https://lab.example" and config["deviceId"] == "d" * 32
    assert config["workerOnly"] is True and config["workerHost"] == "127.0.0.1" and config["workerPort"] == 8765
    assert config["modelPath"].endswith("models/rev1") and config["selfTest"]["coordinator"] is False
    assert "secret-token" not in json.dumps(config)


def test_recipe_v3_admission_is_bound_to_the_boot_and_a_busy_lab_is_retried(tmp_path, monkeypatch):
    worker, _ = paired(tmp_path)
    monkeypatch.setattr(worker_cli.time, "sleep", lambda _: None)
    answers, sent = [LabError(409), LabError(409), {"updated": True}], []

    def call(url, path, token, body, method=None):
        if path == "/api/v1/health":
            return {"recipeVersions": [3]}
        sent.append((path, token, body, method))
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    class Bridge:
        def call(self, action):
            return {"bootId": "boot-7"}

    worker.declare_qualification(Bridge(), worker.settings(), "secret-token", call)

    assert len(sent) == 3 and sent[-1] == (
        "/api/v1/device/qualification",
        "secret-token",
        {"bootId": "boot-7", "selfTest": {**SELF_TEST, "coordinator": False}},
        "PATCH",
    )
    with pytest.raises(LabError):
        answers[:] = [LabError(422)]
        worker.declare_qualification(Bridge(), worker.settings(), "secret-token", call)
