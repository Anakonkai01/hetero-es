"""Draft tests for the next handoff item: a researcher builds a registration manifest without importing ML libraries."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

REVISION = "a" * 40


def snapshot(tmp_path):
    path = tmp_path / "snapshot"
    path.mkdir()
    for name, body in {"config.json": "{}", "tokenizer.json": "{}", "model.safetensors": "fixture weights"}.items():
        (path / name).write_text(body)
    return path


def cli(path, *args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "heteroes",
            "manifest",
            str(path),
            "--model-id",
            "custom/my-model",
            "--revision",
            REVISION,
            *map(str, args),
        ],
        capture_output=True,
        text=True,
    )


def test_a_researcher_builds_the_web_registration_manifest_with_streamed_file_hashes(tmp_path):
    from heteroes.study.models import validate

    path = snapshot(tmp_path)
    result = cli(path)
    assert result.returncode == 0, result.stderr
    manifest = validate(json.loads(result.stdout), allow_any=True)
    assert manifest["modelId"] == "custom/my-model"
    assert manifest["revision"] == manifest["tokenizerRevision"] == REVISION
    assert manifest["files"] == {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in path.iterdir()}
    out = tmp_path / "manifest.json"
    assert cli(path, "--out", out).returncode == 0
    assert json.loads(out.read_text()) == manifest
    before = out.read_bytes()
    assert cli(path, "--out", out).returncode != 0
    assert out.read_bytes() == before


def test_a_manifest_refuses_unsafe_or_incomplete_model_snapshots_and_floating_revisions(tmp_path):
    path = snapshot(tmp_path)
    assert cli(path, "--revision", "main").returncode != 0
    assert cli(path, "--out", path / "manifest.json").returncode != 0
    assert not (path / "manifest.json").exists()
    (path / "remote_code.py").write_text('raise AssertionError("must never run")')
    assert cli(path).returncode != 0
    (path / "remote_code.py").unlink()
    (path / "tokenizer.json").unlink()
    assert cli(path).returncode != 0
