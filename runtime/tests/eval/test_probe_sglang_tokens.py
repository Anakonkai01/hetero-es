"""Comparison evidence must reject different workloads and notice truncated token sequences."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def probe():
    path = Path(__file__).parents[2] / "scripts/probe_sglang_tokens.py"
    spec = importlib.util.spec_from_file_location("sglang_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt(tokens):
    return {
        "status": "ok",
        "workload": {"modelFiles": {"model.safetensors": "abc"}, "maxNewTokens": 3, "promptTokenIds": [[1], [2]]},
        "single": tokens,
        "batched": tokens,
    }


def test_prefix_is_a_difference_at_the_first_missing_token(probe):
    assert probe.compare_tokens([[10, 11], [12]], [[10], [12]]) == {
        "prompts": 2,
        "equal": 1,
        "differences": [{"prompt": 0, "firstDifference": 1, "leftLength": 2, "rightLength": 1}],
    }


def test_missing_rows_cannot_be_hidden_by_zip(probe):
    with pytest.raises(ValueError, match="count"):
        probe.compare_tokens([[1], [2]], [[1]])


@pytest.mark.parametrize(
    "field,value", [("modelFiles", {"model.safetensors": "other"}), ("maxNewTokens", 4), ("promptTokenIds", [[3], [4]])]
)
def test_comparison_requires_identical_inputs_and_generation_limits(probe, field, value):
    left, right = receipt([[1], [2]]), receipt([[1], [2]])
    right["workload"][field] = value
    with pytest.raises(ValueError, match="workload"):
        probe.compare_receipts(left, right)


def test_failed_receipt_cannot_pass_comparison(probe):
    left, right = receipt([[1], [2]]), receipt([[1], [2]])
    right["status"] = "error"
    with pytest.raises(ValueError, match="successful"):
        probe.compare_receipts(left, right)


def test_compare_checks_single_and_batched_independently(probe):
    left, right = receipt([[1], [2]]), receipt([[1], [2]])
    right["batched"] = [[1], [9]]
    result = probe.compare_receipts(left, right)
    assert result["single"]["equal"] == 2
    assert result["batched"]["equal"] == 1


def test_gpu_opt_in_is_checked_before_optional_imports(probe, monkeypatch, tmp_path):
    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE", raising=False)
    with pytest.raises(SystemExit, match="2"):
        probe.main(["--model-path", str(tmp_path), "--out", str(tmp_path / "receipt.json"), "--gpu"])
    assert not (tmp_path / "receipt.json").exists()
