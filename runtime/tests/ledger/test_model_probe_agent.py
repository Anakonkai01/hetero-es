"""Probe command fencing, local ownership and durable reports without GPUs or downloads."""

import json

import pytest

from heteroes.product.files import read_json, write_json
from test_device_agent import agent


def command(**changes):
    return {
        "kind": "QUALIFY_MODEL",
        "commandId": "probe-command",
        "jobId": "c" * 32,
        "mode": "BUILD_REFERENCE",
        "source": "REFERENCE",
        "reference": None,
        "manifest": {
            "formatVersion": 1,
            "modelId": "research/causal-model",
            "revision": "e" * 40,
            "tokenizerRevision": "e" * 40,
            "format": "safetensors",
            "files": {"config.json": "a" * 64, "model.safetensors": "b" * 64, "tokenizer.json": "c" * 64},
        },
        **changes,
    }


def fake_launch(monkeypatch):
    calls = []

    def launch(request):
        from pathlib import Path

        calls.append(request)
        write_json(Path(request["directory"]) / "process.json", {"pid": 123, "birth": "owned"})
        return {"alive": True}

    monkeypatch.setattr("heteroes.product.model_probe_agent.remote_handle", launch)
    monkeypatch.setattr(
        "heteroes.product.agent.owned_state",
        lambda record, intent=False: True if record else (None if intent else False),
    )
    return calls


def test_probe_launches_only_once_after_opt_in_and_keeps_credentials_out_of_argv(tmp_path, monkeypatch):
    a = agent(tmp_path)
    calls = fake_launch(monkeypatch)
    with pytest.raises(RuntimeError):
        a.handle(command())
    assert not calls
    a.enabled = True
    a.handle(command())
    a.handle(command(commandId="retry"))
    assert len(calls) == 1
    argv = calls[0]["argv"]
    assert "--gpu" in argv and "heteroes.product.model_probe" in argv
    assert a.config["deviceToken"] not in json.dumps(argv)
    assert "deviceToken" not in read_json(a.probes.root / ("c" * 32) / "input.json")["config"]
    assert (a.root / "model-probes" / ("c" * 32) / "input.json").stat().st_mode & 0o777 == 0o600


def test_cancel_before_launch_and_off_fence_future_commands(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    calls = fake_launch(monkeypatch)
    a.handle({"kind": "CANCEL_MODEL_QUALIFICATION", "commandId": "cancel", "jobId": "c" * 32})
    a.handle(command())
    assert calls == []
    assert a.probes.reports()[0] == {"jobId": "c" * 32, "status": "CANCELLED", "processAlive": False}
    a.handle(command(jobId="d" * 32, commandId="new"))
    a.cancel_all()
    assert (a.probes.root / ("d" * 32) / "stop.flag").exists()


@pytest.mark.parametrize("ownership", [True, None])
def test_probe_and_training_cannot_overlap_even_with_unknown_ownership(tmp_path, monkeypatch, ownership):
    a = agent(tmp_path)
    a.enabled = True
    calls = fake_launch(monkeypatch)
    root = a.probes.root / ("d" * 32)
    write_json(root / "launch-intent.json", {"started": True})
    if ownership is True:
        write_json(root / "process.json", {"pid": 123, "birth": "owned"})
    with pytest.raises(RuntimeError):
        a.handle(command())
    assert not calls
    with pytest.raises(RuntimeError):
        a.handle(
            {"kind": "START_WORKER", "commandId": "worker", "assignmentId": "b" * 32, "epoch": 1, "workerId": "test"}
        )
    training = a.manager.root / ("e" * 32)
    with pytest.raises(RuntimeError):
        a.manager.launch(training)


def test_probe_cannot_start_during_an_accepted_training_assignment(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    calls = fake_launch(monkeypatch)
    root = a.manager.root / ("d" * 32)
    write_json(root / "assignment.json", {"assignmentId": "e" * 32, "epoch": 1})
    write_json(root / "state.json", {"status": "STARTING"})
    with pytest.raises(RuntimeError):
        a.handle(command())
    assert not calls


def test_unknown_launch_survives_restart_and_a_report_is_acked_only_after_confirmed_death(tmp_path, monkeypatch):
    a = agent(tmp_path)
    fake_launch(monkeypatch)
    root = a.probes.root / ("c" * 32)
    write_json(root / "command.json", {k: v for k, v in command().items() if k not in ("kind", "commandId")})
    write_json(root / "launch-intent.json", {"started": True})
    write_json(root / "result.json", {"status": "COMPLETED", "observations": {"1": [], "-1": []}})
    b = agent(tmp_path)
    assert b.probes.reports()[0]["processAlive"] is None
    b.probes.acknowledge(["c" * 32])
    assert b.probes.reports(), "a transient progress acknowledgement must not discard later completion"
    monkeypatch.setattr("heteroes.product.agent.owned_state", lambda *args, **kwargs: False)
    assert b.probes.reports()[0]["processAlive"] is False
    b.probes.acknowledge(["c" * 32])
    assert b.probes.reports() == []


def test_bad_manifest_and_changed_frozen_job_never_spawn(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    calls = fake_launch(monkeypatch)
    wrong = command()
    wrong["manifest"]["files"]["malicious.py"] = "f" * 64
    with pytest.raises(ValueError):
        a.handle(wrong)
    assert not calls
    a.handle(command())
    with pytest.raises(ValueError):
        a.handle(command(commandId="change", source="UPLOAD"))
    assert len(calls) == 1


def test_desktop_quit_waits_for_model_probe_identity_confirmation(tmp_path, monkeypatch):
    from heteroes.product.desktop_bridge import Bridge

    a = agent(tmp_path)
    bridge = object.__new__(Bridge)
    bridge.agent = a
    write_json(a.probes.root / ("d" * 32) / "launch-intent.json", {"started": True})
    assert bridge.status()["drained"] is False
    monkeypatch.setattr("heteroes.product.agent.owned_state", lambda *args, **kwargs: False)
    assert bridge.status()["drained"] is True


def test_the_probe_process_receives_the_requested_engine_and_decoder(tmp_path, monkeypatch):
    # Earlier the frozen command dropped noiseEngineVersion: a first v2 probe built a v1 reference the lab refused.
    from heteroes.noise.contracts import ENGINE_V2

    a = agent(tmp_path)
    a.enabled = True
    fake_launch(monkeypatch)
    a.handle(command(noiseEngineVersion=ENGINE_V2, decoder="strict_b22_v1"))
    frozen = read_json(a.probes.directory("c" * 32) / "input.json")["command"]
    assert frozen["noiseEngineVersion"] == ENGINE_V2 and frozen["decoder"] == "strict_b22_v1"


def test_an_older_command_without_engine_or_decoder_keeps_its_frozen_bytes(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    fake_launch(monkeypatch)
    a.handle(command())
    frozen = read_json(a.probes.directory("c" * 32) / "command.json")
    assert set(frozen) == {"jobId", "mode", "source", "manifest", "reference"}


def test_an_unknown_probe_decoder_is_refused(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    calls = fake_launch(monkeypatch)
    with pytest.raises(ValueError):
        a.handle(command(decoder="hf_compact"))
    assert not calls
