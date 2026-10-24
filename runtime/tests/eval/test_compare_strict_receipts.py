"""The cross-machine comparison must notice any token/hash difference and refuse failed receipts."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compare_strict_receipts.py"
spec = importlib.util.spec_from_file_location("compare_strict_receipts", SCRIPT)
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


def receipt(tokens, status="ok"):
    case = {"prefillLogitsSha256": "a" * 64, "tokenIds": tokens, "textSha256": "b" * 64, "reward": 1.0}
    return {
        "status": status,
        "environment": {"gpu": "g", "computeCapability": [8, 6], "platform": "p", "torch": "t"},
        "kernelIdentity": {"arch": "sm_86", "nvrtcVersion": [13, 2], "builds": {"ops": {"cubinSha256": "c"}}},
        "timings": [{"tokensPerSecond": 10.0, "perturbSeconds": 0.0, "restoreSeconds": 0.1}],
        "cudaPeakAllocatedBytes": 1,
        "cudaPeakReservedBytes": 2,
        "wallSeconds": 3.0,
        "comparison": {"parentBeforeSha256": "p", "candidates": [{"name": "parent", "prompts": [case]}]},
    }


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def test_identical_receipts_compare_equal_and_inputs_are_hashed(tmp_path):
    paths = [write(tmp_path, f"{n}.json", receipt([1, 2, 3])) for n in ("a", "b", "c")]
    summary = compare.summarize(paths)
    assert summary["comparisonEqual"] and summary["generatedTokensPerMachine"] == 3
    assert set(summary["inputs"]) == {"a.json", "b.json", "c.json"}


def test_one_token_difference_is_reported_with_its_path(tmp_path):
    paths = [write(tmp_path, "a.json", receipt([1, 2, 3])), write(tmp_path, "b.json", receipt([1, 2, 4]))]
    summary = compare.summarize(paths)
    assert not summary["comparisonEqual"]
    assert summary["mismatches"]["b.json"] == ["/candidates[0]/prompts[0]/tokenIds[2]"]
    shorter = write(tmp_path, "c.json", receipt([1, 2]))
    assert compare.summarize([paths[0], shorter])["mismatches"]["c.json"] == ["/candidates[0]/prompts[0]/tokenIds[len]"]


def test_failed_receipts_are_refused(tmp_path):
    paths = [write(tmp_path, "a.json", receipt([1])), write(tmp_path, "b.json", receipt([1], status="error"))]
    with pytest.raises(ValueError):
        compare.summarize(paths)


def test_local_eager_diagnostics_are_reported_but_not_compared(tmp_path):
    checked = receipt([1, 2])
    checked["comparison"]["candidates"][0]["prompts"][0]["eagerPrefillLogitsEqual"] = True
    paths = [write(tmp_path, "a.json", checked), write(tmp_path, "b.json", receipt([1, 2]))]
    summary = compare.summarize(paths)
    assert summary["comparisonEqual"] and summary["eagerPrefillChecks"] == {"a.json": [True]}
