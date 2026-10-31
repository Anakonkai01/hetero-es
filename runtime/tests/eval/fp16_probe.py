"""Measured HF FP16 output references, distinct from strict cross-GPU decoder goldens."""

import json
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parents[1] / "fixtures/archive"


def recorded_fp16_evaluation(gpu_name):
    if gpu_name == "NVIDIA GeForce RTX 5070 Ti":
        path = ARCHIVE / "runtime/artifacts/probes/2026-09-29/probe_5070ti.json"
    elif gpu_name == "NVIDIA GeForce RTX 3060":
        path = ARCHIVE / "docs/evidence/2026-11-01-qwen-fp16-sm86/qwen-fp16-sm86.json"
    else:
        raise ValueError(f"No recorded FP16 reference for {gpu_name}; qualify this GPU explicitly")
    return json.loads(path.read_text(encoding="utf-8"))["base_evaluation"]
