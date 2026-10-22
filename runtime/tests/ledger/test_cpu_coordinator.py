"""CPU coordination proves update arithmetic, without promising GPU-compatible generated texts."""

import copy
import io
import json

import pytest


def test_known_answer_checks_real_update_and_rejects_corruption(monkeypatch):
    from heteroes.product.cpu_coordinator import check_update, UPDATE_EVIDENCE
    import heteroes.es.update as update

    assert check_update() == UPDATE_EVIDENCE
    original = update.apply_coefficients_

    def corrupt(model, *args, **kwargs):
        result = original(model, *args, **kwargs)
        model.w.data[0] = 42
        return result

    monkeypatch.setattr(update, "apply_coefficients_", corrupt)
    with pytest.raises(ValueError, match="update known-answer"):
        check_update()


def test_cpu_qualification_never_runs_a_text_probe_or_claims_a_qualified_model(monkeypatch):
    from heteroes.product import qualification, qualification_v3
    from heteroes.product.cpu_coordinator import qualify, PROFILE, UPDATE_EVIDENCE

    def refuse(*args, **kwargs):
        raise AssertionError("a CPU coordinator never qualifies GPU-compatible texts")

    monkeypatch.setattr(qualification_v3, "observe", refuse)
    monkeypatch.setattr(qualification, "qualify", refuse)
    result = qualify()
    assert result["passed"] is True and result["coordinator"] is True
    assert result["runtimeProfile"] == PROFILE and result["recipeVersions"] == [3]
    assert result["qualifiedModelHashes"] == [] and result["vramTotalMb"] == 0
    assert "gpuUUID" not in result
    from heteroes.product.cpu_coordinator import UPDATE_EVIDENCE_V2

    assert result["compatibility"] == {"updateKnownAnswer": UPDATE_EVIDENCE, "updateKnownAnswerV2": UPDATE_EVIDENCE_V2}
    assert result["environment"]["device"] == "cpu"
    assert result["updateSecondsPerSeed"] is None  # no full-model measurement from a synthetic vector


def test_cpu_entry_point_needs_no_reference_or_model(monkeypatch, capsys):
    from heteroes.product import qualification

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"device": "cpu"})))
    assert qualification.main() == 0
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["result"]
    assert result["runtimeProfile"] == "coordinator-cpu-v3"


def test_cpu_worker_selftest_pairing_and_agent_config(tmp_path):
    from test_worker_cli import bundle, SELF_TEST
    from heteroes.product.cpu_coordinator import qualify

    worker = bundle(tmp_path)
    worker.install(run=lambda *a, **k: None)
    profile = qualify()
    requests = []

    def run(argv, **kwargs):
        assert json.loads(kwargs["input"])["device"] == "cpu"
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == ""
        return type("Done", (), {"stdout": json.dumps({"result": profile})})()

    worker.selftest(run=run, device="cpu")

    def call(url, path, token, body, method=None):
        requests.append((path, body))
        if path == "/api/v1/health":
            return {"agentMode": True}
        return {"deviceId": "d" * 32, "workerId": body["workerId"], "deviceToken": "test-token"}

    with pytest.raises(ValueError, match="coordinator"):
        worker.join("http://127.0.0.1:8790", "test-code", "cpu", call=call)
    worker.join("http://127.0.0.1:8790", "test-code", "cpu", coordinator=True, host="100.64.0.1", call=call)
    config = json.loads(worker.agent_config().read_text())
    assert config["device"] == "cpu" and config["workerOnly"] is False
    assert config["selfTest"]["coordinator"] is True
    assert requests[-1][1]["selfTest"] == profile


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_agent_launch_passes_its_configured_device_to_runner(tmp_path, monkeypatch, device):
    from test_device_agent import agent
    import subprocess

    a = agent(tmp_path)
    a.manager.config["device"] = device
    root = a.manager.root / ("f" * 32)
    root.mkdir()
    launched = []

    def spawn(argv, **kwargs):
        launched.append((argv, kwargs))
        return type("Process", (), {"pid": 987654})()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    a.manager.spawn(root)
    argv, kwargs = launched[0]
    assert argv[-2:] == ["--device", device]
    if device == "cpu":
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == ""


def test_cpu_agent_refuses_a_worker_start(tmp_path):
    from test_device_agent import agent

    a = agent(tmp_path)
    a.config.update(device="cpu", selfTest={"runtimeProfile": "coordinator-cpu-v3"})
    a.enabled = True
    command = {"assignmentId": "b" * 32, "epoch": 1, "runId": "c" * 32, "workerId": "test"}
    with pytest.raises(ValueError, match="coordinator-only"):
        a._worker(command, "start")
