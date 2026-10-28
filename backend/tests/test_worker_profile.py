"""The desktop worker profile generator writes only a fresh directory and binds the selected reference."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/build-worker-profile.py"


@pytest.fixture
def builder(monkeypatch):
    spec = importlib.util.spec_from_file_location("build_worker_profile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    release = {
        "assets": [
            {
                "name": f"cpython-3.12.15+20261009-{target}-install_only_stripped.tar.gz",
                "browser_download_url": f"https://example.invalid/{target}.tar.gz",
                "digest": "sha256:" + "a" * 64,
                "size": 100,
            }
            for target in ("x86_64-pc-windows-msvc", "x86_64-unknown-linux-gnu")
        ]
    }
    monkeypatch.setattr(module, "fetch_release", lambda: release)
    monkeypatch.setattr(module, "get_size", lambda url: 7)
    return module


def report(*names):
    return {
        "install": [
            {
                "download_info": {
                    "url": f"https://files.example.invalid/{name}",
                    "archive_info": {"hashes": {"sha256": hashlib.sha256(name.encode()).hexdigest()}},
                },
                "metadata": {"name": name.split("-")[0], "version": name.split("-")[1]},
            }
            for name in names
        ]
    }


@pytest.fixture
def inputs(tmp_path):
    track = tmp_path / "runtime"
    (track / "src/heteroes").mkdir(parents=True)
    (track / "src/heteroes/__init__.py").write_text("")
    (track / "scripts").mkdir()
    (track / "scripts/run_worker.py").write_text("print('worker')\n")
    legacy = track / "references"
    legacy.mkdir(parents=True)
    (legacy / "desktop-v1-reference.json").write_text('{"profile": "desktop-v1"}\n')
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "linux.json").write_text(json.dumps(report("peft-0.21.2-py3-none-any.whl", "torch-2.13.0-linux.whl")))
    (reports / "windows.json").write_text(json.dumps(report("peft-0.21.2-py3-none-any.whl", "torch-2.13.0-win.whl")))
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    for name in ("config.json", "generation_config.json", "model.safetensors", "tokenizer.json"):
        (snapshot / name).write_text(name)
    for name in ("tokenizer_config.json", "vocab.json", "merges.txt"):
        (snapshot / name).write_text(name)
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / "reference-v3-adapter.bin").write_bytes(b"adapter")
    body = {
        "formatVersion": 3,
        "profile": "desktop-v3",
        "adapter": {"file": "reference-v3-adapter.bin", "sha256": hashlib.sha256(b"adapter").hexdigest()},
    }
    (reference / "reference-v3.json").write_text(json.dumps(body))
    common = ["--track-a", str(track), "--reports", str(reports), "--model-snapshot", str(snapshot)]
    return {"common": common, "reference": reference, "track": track, "tmp": tmp_path}


def test_a_v3_profile_is_written_to_a_fresh_directory_with_its_reference(builder, inputs):
    out = inputs["tmp"] / "out"
    builder.main(
        [*inputs["common"], "--profile", "desktop-v3", "--reference-dir", str(inputs["reference"]), "--out", str(out)]
    )
    profile = json.loads((out / "profile.json").read_text())
    assert profile["profile"] == "desktop-v3"
    assert json.loads((out / "reference.json").read_text()) == json.loads(
        (inputs["reference"] / "reference-v3.json").read_text()
    )
    assert (out / "reference-v3-adapter.bin").read_bytes() == b"adapter"
    assert profile["runtimeSha256"] == hashlib.sha256((out / "runtime.tar.gz").read_bytes()).hexdigest()
    lock = (out / "requirements-windows.txt").read_text().splitlines()
    assert lock == sorted(lock) and all("--hash=sha256:" in line for line in lock)
    assert [w["sizeBytes"] for w in profile["platforms"]["windows"]["wheels"]] == [7, 7]
    assert len(profile["modelFiles"]) == 7
    for source in inputs["track"].rglob("*.py"):  # a checkout at another time gives the same archive
        os.utime(source, (1_000_000_000, 1_000_000_000))
    again = inputs["tmp"] / "again"
    builder.main(
        [*inputs["common"], "--profile", "desktop-v3", "--reference-dir", str(inputs["reference"]), "--out", str(again)]
    )
    assert (again / "runtime.tar.gz").read_bytes() == (out / "runtime.tar.gz").read_bytes()  # reproducible


def test_the_legacy_profile_keeps_its_reference(builder, inputs):
    out = inputs["tmp"] / "v1"
    builder.main([*inputs["common"], "--profile", "desktop-v1", "--out", str(out)])
    assert json.loads((out / "profile.json").read_text())["profile"] == "desktop-v1"
    assert (out / "reference.json").read_text() == '{"profile": "desktop-v1"}\n'
    assert not (out / "reference-v3-adapter.bin").exists()


@pytest.mark.parametrize(
    "problem", ["exists", "adapter", "legacy-reference", "v3-without-reference", "v1-with-reference", "linux-wheel"]
)
def test_unsafe_requests_leave_nothing_behind(builder, inputs, problem):
    out = inputs["tmp"] / "out"
    selection = ["--profile", "desktop-v3", "--reference-dir", str(inputs["reference"])]
    if problem == "exists":
        out.mkdir()
    elif problem == "adapter":
        (inputs["reference"] / "reference-v3-adapter.bin").write_bytes(b"other")
    elif problem == "legacy-reference":
        (inputs["reference"] / "reference-v3.json").write_text('{"profile": "desktop-v1"}')
    elif problem == "v3-without-reference":
        selection = ["--profile", "desktop-v3"]
    elif problem == "v1-with-reference":
        selection = ["--profile", "desktop-v1", "--reference-dir", str(inputs["reference"])]
    else:
        reports = Path(inputs["common"][3])
        (reports / "windows.json").write_text(json.dumps(report("torch-2.13.0-manylinux_x86_64.whl")))
    with pytest.raises((ValueError, FileExistsError, SystemExit)):
        builder.main([*inputs["common"], *selection, "--out", str(out)])
    assert sorted(p.name for p in inputs["tmp"].iterdir() if p.name.startswith("out")) == (
        ["out"] if problem == "exists" else []
    )
    if problem == "exists":
        assert not any(out.iterdir())


def test_a_missing_report_hash_comes_only_from_the_same_url_in_a_reviewed_profile(builder, inputs):
    reports = Path(inputs["common"][3])
    for platform in ("linux", "windows"):
        body = json.loads((reports / f"{platform}.json").read_text())
        body["install"][1]["download_info"]["archive_info"] = {}  # the PyTorch index gave no hash
        (reports / f"{platform}.json").write_text(json.dumps(body))
    selection = ["--profile", "desktop-v3", "--reference-dir", str(inputs["reference"])]
    with pytest.raises(ValueError, match="no hash"):
        builder.main([*inputs["common"], *selection, "--out", str(inputs["tmp"] / "unpinned")])
    torch = {p: json.loads((reports / f"{p}.json").read_text())["install"][1] for p in ("linux", "windows")}
    reviewed = {
        "platforms": {
            p: {"wheels": [{"url": row["download_info"]["url"], "sha256": "b" * 64}]} for p, row in torch.items()
        }
    }
    pinned = inputs["tmp"] / "reviewed.json"
    pinned.write_text(json.dumps(reviewed))
    out = inputs["tmp"] / "pinned"
    builder.main([*inputs["common"], *selection, "--pinned-profile", str(pinned), "--out", str(out)])
    assert f"torch==2.13.0 --hash=sha256:{'b' * 64}" in (out / "requirements-linux.txt").read_text()
    reviewed["platforms"]["windows"]["wheels"][0]["url"] += "?mirror"  # another URL is not the reviewed object
    pinned.write_text(json.dumps(reviewed))
    with pytest.raises(ValueError, match="no hash"):
        builder.main(
            [*inputs["common"], *selection, "--pinned-profile", str(pinned), "--out", str(inputs["tmp"] / "x")]
        )
    assert not (inputs["tmp"] / "x").exists() and not (inputs["tmp"] / "unpinned").exists()


def test_a_size_lookup_retries_transient_network_errors_a_bounded_number_of_times(monkeypatch):
    import urllib.error

    spec = importlib.util.spec_from_file_location("build_worker_profile_sizes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class Response:
        headers = {"Content-Range": "bytes 0-0/1234"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def flaky(request, timeout):
        calls.append(request.full_url)
        if len(calls) < module.SIZE_ATTEMPTS:
            raise urllib.error.URLError("handshake timed out")
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    assert module.get_size("https://files.example.invalid/a.whl") == 1234
    assert len(calls) == module.SIZE_ATTEMPTS
    calls.clear()

    def down(request, timeout):
        calls.append(request.full_url)
        raise urllib.error.URLError("handshake timed out")

    monkeypatch.setattr(module.urllib.request, "urlopen", down)
    with pytest.raises(urllib.error.URLError):
        module.get_size("https://files.example.invalid/a.whl")
    assert len(calls) == module.SIZE_ATTEMPTS  # bounded, then the error is reported
