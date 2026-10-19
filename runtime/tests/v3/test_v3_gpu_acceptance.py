"""The GPU qualification gate and comparison contract are testable without CUDA."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def probe():
    path = Path(__file__).resolve().parents[2] / "scripts/v3_gpu_acceptance.py"
    spec = importlib.util.spec_from_file_location("v3_gpu_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gpu_requires_both_owner_gate_and_explicit_flag(probe, monkeypatch):
    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE", raising=False)
    with pytest.raises(ValueError, match="HETEROES_GPU_ACCEPTANCE"):
        probe.require_gpu(True)
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    with pytest.raises(ValueError, match="--gpu"):
        probe.require_gpu(False)
    probe.require_gpu(True)


def test_cross_gpu_comparison_rejects_text_or_identity_drift(probe):
    import copy

    receipt = {
        "sourceTreeSha256": "code",
        "recipeHash": "recipe",
        "planHash": "plan",
        "candidates": [{"candidateId": "candidate", "texts": ["Answer: 7"], "reward": 1.0}],
        "children": ["child"],
        "replayPassed": True,
        "auditCount": 8,
        "auditMismatches": 0,
    }
    assert probe.compare(receipt, copy.deepcopy(receipt))["passed"]
    for field, replacement in (
        ("recipeHash", "other"),
        ("sourceTreeSha256", "other"),
        ("children", ["other"]),
        ("replayPassed", False),
        ("auditMismatches", 1),
    ):
        bad = {**receipt, field: replacement}
        with pytest.raises(ValueError):
            probe.compare(receipt, bad)
    bad = copy.deepcopy(receipt)
    bad["candidates"][0]["texts"] = ["Answer: 8"]
    with pytest.raises(ValueError):
        probe.compare(receipt, bad)
