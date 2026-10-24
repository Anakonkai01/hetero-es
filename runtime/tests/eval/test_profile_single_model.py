"""The lifecycle probe is CPU by default and never substitutes a two-model or unapproved GPU baseline."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "profile_single_model.py"


def probe():
    spec = importlib.util.spec_from_file_location("profile_single_model", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_evidence_is_refused_before_loading_a_model(tmp_path):
    out = tmp_path / "receipt.json"
    out.write_text("preserve this receipt")

    with pytest.raises(SystemExit):
        probe().main(["--model-path", str(tmp_path / "missing"), "--out", str(out)])

    assert out.read_text() == "preserve this receipt"


@pytest.mark.parametrize("extra,acceptance", [((), "1"), (("--gpu",), "0"), (("--gpu",), "")])
def test_cuda_needs_both_gpu_flag_and_acceptance_environment(tmp_path, monkeypatch, extra, acceptance):
    import torch

    def forbidden_probe():
        raise AssertionError("The authorization guard must run before any CUDA availability probe")

    monkeypatch.setattr(torch.cuda, "is_available", forbidden_probe)
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", acceptance)
    out = tmp_path / "receipt.json"
    with pytest.raises(SystemExit):
        probe().main(["--model-path", str(tmp_path / "missing"), "--out", str(out), "--device", "cuda", *extra])
    assert not out.exists()


def test_cpu_fixture_runs_one_model_and_records_real_generation_restore_and_phase_data(tmp_path):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "v3"))
    from tinylm import build_tiny_lm

    model = build_tiny_lm(tmp_path / "model")
    out = tmp_path / "receipt.json"

    assert (
        probe().main(
            [
                "--model-path",
                str(model),
                "--out",
                str(out),
                "--candidates",
                "1",
                "--max-new-tokens",
                "2",
                "--prompt",
                "2+2=",
                "--threads",
                "2",
            ]
        )
        == 0
    )

    receipt = json.loads(out.read_text())
    assert receipt["status"] == "ok" and receipt["device"] == "cpu"
    assert receipt["inferenceBackend"] == "hf_native_fp16_baseline" and receipt["strictInference"] is False
    assert receipt["parentBeforeSha256"] == receipt["parentAfterSha256"]
    assert receipt["storage"]["roles"].keys() == {"inference"}
    assert receipt["storage"]["unique"] == receipt["storage"]["roles"]["inference"]
    assert receipt["snapshotBytes"] > 0 and receipt["cudaPeakAllocatedBytes"] is None
    assert len(receipt["samples"]) == 1 and 0 < len(receipt["samples"][0]["tokenIds"]) <= 2
    assert receipt["samples"][0]["restoreExact"] is True
    phases = [event["phase"] for event in receipt["phases"]]
    assert all(
        phase in phases for phase in ("model_files_hash", "model_load", "snapshot", "perturb", "rollout", "restore")
    )
    assert all(event["timingKind"] == "host_wall" for event in receipt["phases"])
    assert "not a cross-device equality test" in receipt["limitations"]


def test_reference_probe_wraps_one_loaded_model_and_records_its_experimental_identity(tmp_path, monkeypatch):
    import sys

    from heteroes.eval import qwen2_reference
    from heteroes.v3 import model as model_loader

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "v3"))
    from tinylm import build_tiny_lm

    model_path = build_tiny_lm(tmp_path / "model")
    out = tmp_path / "reference.json"
    load, reference = model_loader.load, qwen2_reference.Qwen2Reference
    loaded, wrapped = [], []

    def tracked_load(*args):
        result = load(*args)
        loaded.append(result[0])
        return result

    def fixture_reference(model):
        result = reference(model, max_context=64, allow_fixture=True)
        wrapped.append(result)
        return result

    monkeypatch.setattr(model_loader, "load", tracked_load)
    monkeypatch.setattr(qwen2_reference, "Qwen2Reference", fixture_reference)
    assert (
        probe().main(
            [
                "--model-path",
                str(model_path),
                "--out",
                str(out),
                "--backend",
                "qwen2-reference",
                "--candidates",
                "1",
                "--max-new-tokens",
                "2",
                "--prompt",
                "2+2=",
            ]
        )
        == 0
    )
    receipt = json.loads(out.read_text())
    assert len(loaded) == len(wrapped) == 1 and wrapped[0].model is loaded[0]
    assert receipt["inferenceBackend"] == qwen2_reference.REFERENCE_BACKEND
    assert receipt["backendIdentity"] == wrapped[0].identity
    assert receipt["backendFingerprint"] == wrapped[0].fingerprint
    assert receipt["strictInference"] is False and not receipt["backendIdentity"]["hardwareQualified"]
    assert receipt["parentBeforeSha256"] == receipt["parentAfterSha256"]
    assert receipt["samples"][0]["restoreExact"] is True
    assert receipt["samples"][0]["tokenIds"]
    # Same backing weights under both roles, with only the tiny RoPE buffer added by the reference.
    assert receipt["storage"]["unique"]["cpu"]["storageBytes"] < receipt["snapshotBytes"] + 1024
