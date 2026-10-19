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


def test_probe_uses_valid_scorer_and_numeric_answers(probe):
    from heteroes.v3.local import _scorer_spec
    from heteroes.v3.scoring import validate_spec

    for space in ("full", "subset", "lora"):
        spec = probe.configuration(Path("model"), Path("rows.json"), space)
        scorer, _ = _scorer_spec(spec)
        validate_spec(scorer)
    assert all(type(row["answer"]) is int for row in probe.qualification_rows())


def test_source_identity_uses_portable_relative_paths(probe):
    posix = {"v3/run.py": "a" * 64, "__init__.py": "b" * 64}
    windows = {"v3\\run.py": "a" * 64, "__init__.py": "b" * 64}
    assert probe.portable_identity(posix) == probe.portable_identity(windows)


def test_bulk_weights_stay_outside_private_run_state(probe, tmp_path):
    out, bulk = tmp_path / "private", tmp_path / "bulk"
    out.mkdir()
    probe.prepare_bulk_paths(out, bulk)
    (out / "run/published/checkpoint.bin").write_bytes(b"weights")
    (out / "run/ledger.sqlite").write_bytes(b"private state")
    assert (bulk / "published/checkpoint.bin").read_bytes() == b"weights"
    assert not (bulk / "ledger.sqlite").exists()
    with pytest.raises(FileExistsError):
        probe.prepare_bulk_paths(out, bulk)
