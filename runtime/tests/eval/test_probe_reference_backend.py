"""The portable hardware probe must produce comparable facts without certifying itself."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "probe_reference_backend.py"


def probe():
    spec = importlib.util.spec_from_file_location("probe_reference_backend", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("gpu,acceptance", [(False, "1"), (True, "0")])
def test_gpu_probe_rejects_missing_authorization_before_loading_cuda(tmp_path, monkeypatch, gpu, acceptance):
    import torch

    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", acceptance)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: pytest.fail("guard must run first"))
    with pytest.raises(SystemExit):
        probe().main(["--out", str(tmp_path / "gpu.json"), "--device", "cuda", *(["--gpu"] if gpu else [])])


def test_cpu_probe_reports_reproducible_bits_tokens_parent_restore_and_limits(tmp_path):
    receipts = []
    for name in ("first", "second"):
        path = tmp_path / f"{name}.json"
        assert probe().main(["--out", str(path)]) == 0
        receipts.append(json.loads(path.read_text()))
    first, second = receipts
    assert first["status"] == "ok" and not first["hardwareQualified"]
    assert first["comparison"] == second["comparison"]
    comparison = first["comparison"]
    assert comparison["parentBeforeSha256"] == comparison["parentAfterSha256"]
    assert comparison["candidateSha256"] != comparison["parentBeforeSha256"]
    assert comparison["restoreExact"] is True
    assert len(comparison["cases"]) == 4
    assert {case["state"] for case in comparison["cases"]} == {"parent", "candidate"}
    assert all(case["tokenIds"] and case["logitsSha256"] for case in comparison["cases"])
    assert set(comparison["operatorHashes"]) >= {"linear", "rmsNorm", "softmax", "sin", "cos", "silu", "edgeArithmetic"}
    assert first["storage"]["unique"]["cpu"]["storageBytes"] < first["snapshotBytes"] + 1024
    assert "fixture" in first["limitations"].lower()


def test_probe_never_rewrites_an_existing_receipt(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text("keep")
    with pytest.raises(SystemExit):
        probe().main(["--out", str(path)])
    assert path.read_text() == "keep"
