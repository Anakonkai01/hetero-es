"""GPU suites must use a copy named for the pinned model revision before collecting real-model tests."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"


def model_source(tmp_path):
    models = tmp_path / "models"
    source = models / "qwen"
    source.mkdir(parents=True)
    (source / "config.json").write_text('{"model_type":"qwen2"}')
    (source / "model.safetensors").write_bytes(b"fixture-only model")
    return models, source


def test_pinned_model_view_preserves_source_files_and_has_revision_name(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "runtime/src"))
    from acceptance.probes.pytest_gpu_suite import prepare_model_view

    models, source = model_source(tmp_path)
    out = tmp_path / "probe"
    view = prepare_model_view(models, out)
    assert view.name == REVISION
    assert view.resolve().name == REVISION
    assert (view / "model.safetensors").read_bytes() == b"fixture-only model"
    assert not (view / "model.safetensors").is_symlink()
    (view / "config.json").write_text("modified view")
    assert (source / "config.json").read_text() == '{"model_type":"qwen2"}'
    metadata = json.loads((out / "model-view.json").read_text())
    assert metadata["revision"] == REVISION and metadata["source"] == str(source.resolve())


def test_missing_model_fails_before_creating_a_view(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "runtime/src"))
    from acceptance.probes.pytest_gpu_suite import prepare_model_view

    with pytest.raises((FileNotFoundError, ValueError)):
        prepare_model_view(tmp_path / "missing", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_wrapper_sets_model_environment_before_pytest_collection(tmp_path):
    models, _ = model_source(tmp_path)
    test = tmp_path / "test_model_environment.py"
    test.write_text(
        "import os\nfrom pathlib import Path\n"
        "model = Path(os.environ['HETEROES_QWEN_PINNED_PATH'])\n"
        f"def test_model_view():\n    assert model.name == {REVISION!r}\n"
        "    assert (model / 'model.safetensors').read_bytes() == b'fixture-only model'\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "acceptance/probes/pytest_gpu_suite.py"),
            "--models",
            str(models),
            "--out",
            str(tmp_path / "probe"),
            "--",
            "-q",
            str(test),
        ],
        env={**os.environ, "PYTHONPATH": str(REPO / "runtime/src"), "CUDA_VISIBLE_DEVICES": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
