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
