"""The trusted child can build and compare a tiny CPU reference; this is not GPU acceptance."""

import json
import os
from pathlib import Path
import subprocess
import sys

from heteroes.product.files import write_json
from heteroes.v3.model import registration_manifest
from tinylm import build_tiny_lm


def test_child_builds_and_compares_a_reference_without_researcher_code(tmp_path):
    model = tmp_path / "model"
    build_tiny_lm(model)
    manifest = registration_manifest(model, "research/new-model", "e" * 40)
    from heteroes.canonical import canonical_json_hash

    config = {"modelPaths": {canonical_json_hash(manifest): str(model)}}
    reference = None
    for mode in ("BUILD_REFERENCE", "COMPARE_REFERENCE"):
        root = tmp_path / mode
        write_json(
            root / "input.json",
            {
                "command": {
                    "jobId": "a" * 32,
                    "mode": mode,
                    "manifest": manifest,
                    "reference": reference,
                    "source": "REFERENCE",
                },
                "config": config,
                "stateDirectory": str(tmp_path / "state"),
            },
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "heteroes.product.model_probe",
                "--input",
                str(root / "input.json"),
                "--device",
                "cpu",
            ],
            env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((root / "result.json").read_text())
        assert report["status"] == "COMPLETED"
        assert set(report["observations"]) == {"1", "-1"}
        if reference is None:
            reference = report["reference"]
        else:
            assert report["reference"] is None
    assert not list(model.glob("*.bin"))


def test_child_requires_gpu_opt_in_and_honors_cancel_before_loading(tmp_path):
    source = tmp_path / "input.json"
    write_json(source, {"command": {}, "config": {}, "stateDirectory": str(tmp_path)})
    result = subprocess.run(
        [sys.executable, "-m", "heteroes.product.model_probe", "--input", str(source)],
        env={**os.environ, "HETEROES_GPU_ACCEPTANCE": "0"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    (tmp_path / "stop.flag").touch()
    result = subprocess.run(
        [sys.executable, "-m", "heteroes.product.model_probe", "--input", str(source), "--device", "cpu"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads((tmp_path / "result.json").read_text()) == {"status": "CANCELLED"}


def test_child_reports_restore_failure_without_foreign_exception_text(tmp_path, monkeypatch):
    from heteroes.product.model_probe import run
    from heteroes.worker import CandidateFailed
    from heteroes.ledger import FailureKind

    model = tmp_path / "model"
    build_tiny_lm(model)
    manifest = registration_manifest(model, "research/new-model", "e" * 40)
    write_json(
        tmp_path / "input.json",
        {
            "command": {
                "jobId": "a" * 32,
                "mode": "BUILD_REFERENCE",
                "manifest": manifest,
                "reference": None,
                "source": "REFERENCE",
            },
            "config": {},
            "stateDirectory": str(tmp_path / "state"),
        },
    )
    monkeypatch.setattr("heteroes.study.prepare.prepare_model", lambda *a, **kw: model)

    def fail(*args, **kwargs):
        raise CandidateFailed(FailureKind.RESTORE_MISMATCH, "private-transfer-grant-never-report")

    monkeypatch.setattr("heteroes.product.model_qualification.build_reference", fail)
    assert run(tmp_path / "input.json", "cpu") == {"status": "FAILED", "errorCode": "RESTORE_MISMATCH"}


def test_child_builds_the_reference_for_the_commanded_engine_and_decoder(tmp_path, monkeypatch):
    from heteroes.noise.contracts import ENGINE_V2
    from heteroes.product.model_probe import run

    model = tmp_path / "model"
    build_tiny_lm(model)
    manifest = registration_manifest(model, "research/new-model", "e" * 40)
    seen = []

    def build(*args, **kwargs):
        seen.append(kwargs)
        return {"reference": True}, {"1": [], "-1": []}

    monkeypatch.setattr("heteroes.study.prepare.prepare_model", lambda *a, **kw: model)
    monkeypatch.setattr("heteroes.product.model_qualification.build_reference", build)
    for extra in ({"noiseEngineVersion": ENGINE_V2, "decoder": "strict_b22_v1"}, {}):
        write_json(
            tmp_path / "input.json",
            {
                "command": {
                    "jobId": "a" * 32,
                    "mode": "BUILD_REFERENCE",
                    "manifest": manifest,
                    "reference": None,
                    "source": "REFERENCE",
                    **extra,
                },
                "config": {},
                "stateDirectory": str(tmp_path / "state"),
            },
        )
        assert run(tmp_path / "input.json", "cpu")["status"] == "COMPLETED"
    assert seen[0] == {"engine": ENGINE_V2, "decoder": "strict_b22_v1"}
    assert seen[1]["decoder"] == "hf_generate" and seen[1]["engine"] != ENGINE_V2  # older commands keep the plain probe
