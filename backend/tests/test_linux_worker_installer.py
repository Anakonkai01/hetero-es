"""The one-line Linux Worker installer, run for real against file:// downloads (fake Python whose pip is a no-op)."""

import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("build_linux_worker", ROOT / "scripts/build-linux-worker.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def tar_gz(path, members):
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, data, mode in members:
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), mode
                archive.addfile(info, io.BytesIO(data))


def pinned(path, data):
    path.write_bytes(data)
    return {"name": path.name, "url": path.as_uri(), "sha256": hashlib.sha256(data).hexdigest(), "sizeBytes": len(data)}


@pytest.fixture
def release(tmp_path):
    resources, source = tmp_path / "resources", tmp_path / "source"
    resources.mkdir()
    source.mkdir()
    runtime_src = ROOT / "runtime"
    tar_gz(
        resources / "runtime.tar.gz",
        [
            (str(f.relative_to(runtime_src)), f.read_bytes(), 0o644)
            for f in sorted((runtime_src / "src/heteroes").rglob("*.py"))
        ],
    )
    fake_python = f'#!/bin/sh\n[ "$1 $2" = "-m pip" ] && exit 0\nexec {sys.executable} "$@"\n'.encode()
    tar_gz(source / "python.tar.gz", [("python/bin/python3.12", fake_python, 0o755)])
    for name in ("requirements-linux.txt", "reference.json", "reference-v3-adapter.bin"):
        (resources / name).write_text("")
    profile = {
        "profile": "desktop-v3",
        "modelRevision": "rev1",
        "runtimeSha256": hashlib.sha256((resources / "runtime.tar.gz").read_bytes()).hexdigest(),
        "modelFiles": [pinned(source / "model.safetensors", b"weights")],
        "platforms": {
            "linux": {
                "python": pinned(source / "python.tar.gz", (source / "python.tar.gz").read_bytes()),
                "lockFile": "requirements-linux.txt",
                "wheels": [pinned(source / "x-1-py3-none-any.whl", b"wheel")],
            }
        },
    }
    (resources / "profile.json").write_text(json.dumps(profile))
    out = tmp_path / "out"
    builder.build(resources, out, "test1", "https://lab.invalid/downloads")
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "user"),
        "HETEROES_WORKER_HOME": str(tmp_path / "user/worker"),
        "HETEROES_BIN_DIR": str(tmp_path / "user/bin"),
        "HETEROES_BUNDLE": str(out / "heteroes-worker-linux-test1.tar.gz"),
    }
    return out, env


def test_the_installer_puts_the_pinned_runtime_model_and_command_in_place(release):
    out, env = release
    installed = subprocess.run(["bash", out / "install-worker.sh"], env=env, capture_output=True, text=True)
    assert installed.returncode == 0, installed.stderr

    home = Path(env["HETEROES_WORKER_HOME"])
    assert (home / "models/rev1/model.safetensors").read_bytes() == b"weights"
    status = subprocess.run(
        [Path(env["HETEROES_BIN_DIR"]) / "heteroes-worker", "status", "--json"], env=env, capture_output=True
    )
    assert json.loads(status.stdout)["installed"] is True
    again = subprocess.run(["bash", out / "install-worker.sh"], env=env, capture_output=True, text=True)
    assert again.returncode == 0, again.stderr  # a second run is a no-op upgrade


def test_a_bundle_that_does_not_match_the_pinned_checksum_installs_nothing(release, tmp_path):
    out, env = release
    tampered = tmp_path / "tampered.tar.gz"
    tampered.write_bytes(Path(env["HETEROES_BUNDLE"]).read_bytes() + b"x")

    result = subprocess.run(
        ["bash", out / "install-worker.sh"],
        env={**env, "HETEROES_BUNDLE": str(tampered)},
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0 and "checksum mismatch" in result.stderr
    assert not (Path(env["HETEROES_WORKER_HOME"]) / "bundle").exists()
    assert not (Path(env["HETEROES_BIN_DIR"]) / "heteroes-worker").exists()


def test_the_builder_refuses_resources_whose_runtime_does_not_match_the_profile(release, tmp_path):
    resources = tmp_path / "resources"
    (resources / "runtime.tar.gz").write_bytes(b"other")
    with pytest.raises(RuntimeError, match="does not match"):
        builder.build(resources, tmp_path / "out2", "test2", "https://lab.invalid/downloads")


def test_an_update_with_the_same_pinned_packages_reuses_them_instead_of_downloading(release, tmp_path):
    # 2026-10-22: every update fetched 2.7 GB of wheels again and its disk check refused a nearly full disk
    out, env = release
    assert subprocess.run(["bash", out / "install-worker.sh"], env=env, capture_output=True).returncode == 0
    home = Path(env["HETEROES_WORKER_HOME"])
    [first] = list((home / "runtimes").iterdir())
    resources = tmp_path / "resources"
    runtime_src = ROOT / "runtime"
    sources = [
        (str(f.relative_to(runtime_src)), f.read_bytes(), 0o644)
        for f in sorted((runtime_src / "src/heteroes").rglob("*.py"))
    ]
    tar_gz(resources / "runtime.tar.gz", sources + [("src/heteroes/NEWER.txt", b"a newer HeteroES\n", 0o644)])
    profile = json.loads((resources / "profile.json").read_text())
    profile["runtimeSha256"] = hashlib.sha256((resources / "runtime.tar.gz").read_bytes()).hexdigest()
    (resources / "profile.json").write_text(json.dumps(profile))
    builder.build(resources, tmp_path / "out2", "test2", "https://lab.invalid/downloads")
    (tmp_path / "source/python.tar.gz").unlink()  # nothing may be downloaded again
    for cached in (home / "downloads").glob("*python*"):
        cached.unlink()
    updated = subprocess.run(
        ["bash", tmp_path / "out2/install-worker.sh"],
        env={**env, "HETEROES_BUNDLE": str(tmp_path / "out2/heteroes-worker-linux-test2.tar.gz")},
        capture_output=True,
        text=True,
    )
    assert updated.returncode == 0, updated.stderr
    assert "reusing the pinned Python and packages" in updated.stdout
    second = home / "runtimes" / profile["runtimeSha256"][:12]
    assert (second / "python/bin/python3.12").stat().st_ino == (first / "python/bin/python3.12").stat().st_ino
    assert (second / "src/heteroes/NEWER.txt").read_text() == "a newer HeteroES\n"
    assert second.name in (Path(env["HETEROES_BIN_DIR"]) / "heteroes-worker").read_text()
