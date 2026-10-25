"""Finite numerical-comparison reporting must preserve counterexamples and reject invalid metrics."""

import importlib.util
from pathlib import Path

import pytest
import torch


def script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "probe_integer_decoder.py"
    spec = importlib.util.spec_from_file_location("probe_integer_decoder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_logit_metrics_detect_argmax_flip_and_keep_zero_reference_error_defined():
    reference = torch.tensor([[1.0, 0.0], [0.0, 1.0]])
    actual = torch.tensor([[0.0, 1.0], [0.0, 1.0]])
    result = script().logit_metrics(reference, actual)
    assert result["top1EqualRows"] == 1 and result["rows"] == 2
    assert result["maxAbsoluteError"] == 1.0
    assert result["relativeRmsError"] == pytest.approx(1.0)
    assert result["meanKLDivergence"] > 0
    zero = script().logit_metrics(torch.zeros(1, 2), torch.ones(1, 2))
    assert zero["relativeRmsError"] is None and zero["rmsError"] == 1
    same = script().logit_metrics(reference, reference)
    assert same["top1EqualRows"] == 2 and same["meanKLDivergence"] == 0


@pytest.mark.parametrize("actual", [torch.ones(1, 2), torch.tensor([[float("nan"), 0.0], [0.0, 1.0]])])
def test_invalid_logit_comparison_is_not_a_passing_zero_error(actual):
    with pytest.raises(ValueError):
        script().logit_metrics(torch.zeros(2, 2), actual)


def test_token_comparison_records_first_divergence_and_does_not_truncate_missing_outputs():
    result = script().token_comparison([[1, 2, 3], [5, 6]], [[1, 2, 4], [5, 6]])
    assert result == {
        "rows": 2,
        "equalRows": 1,
        "equalTokenPositions": 4,
        "totalTokenPositions": 5,
        "firstDivergence": [2, None],
    }
    with pytest.raises(ValueError):
        script().token_comparison([[1, 2]], [[1]])


def test_probe_guard_precedes_torch_and_model_loading(tmp_path, monkeypatch):
    module = script()
    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE", raising=False)
    with pytest.raises(SystemExit):
        module.main(["--model-path", str(tmp_path), "--out", str(tmp_path / "r.json")])
