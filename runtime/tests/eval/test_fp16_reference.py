"""HF FP16 references are measured per GPU; strict inference has its own cross-GPU goldens."""

import pytest

from fp16_probe import recorded_fp16_evaluation


def test_original_5070ti_probe_is_preserved():
    result = recorded_fp16_evaluation("NVIDIA GeForce RTX 5070 Ti")
    assert result["mean_reward"] == 0.25
    assert len(result["records"]) == 16
    assert result["records"][5]["output_text"] == "664"


def test_3060_uses_its_independently_captured_exact_reference():
    original = recorded_fp16_evaluation("NVIDIA GeForce RTX 5070 Ti")
    result = recorded_fp16_evaluation("NVIDIA GeForce RTX 3060")
    assert result["mean_reward"] == 0.25
    assert len(result["records"]) == 16
    assert result["records"][5]["output_text"] == "674"
    assert result["records"][5]["prediction"] == 674
    assert result["records"][5]["reward"] == 0.0
    assert [a == b for a, b in zip(original["records"], result["records"], strict=True)] == [
        True,
        True,
        True,
        True,
        True,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    ]


def test_unmeasured_gpu_cannot_silently_reuse_another_devices_fp16_reference():
    with pytest.raises(ValueError, match="No recorded FP16 reference"):
        recorded_fp16_evaluation("NVIDIA GeForce RTX 3090")
