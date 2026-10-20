"""Preparing reviewable installers must not publish them on the live site."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
import pytest


def test_prepare_only_builds_four_hashed_installers_without_touching_public_manifest(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / "scripts/publish-local-installers.py"
    spec = importlib.util.spec_from_file_location("prepare_installers", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fake_repo = tmp_path / "repo"
    links = fake_repo / "frontend/public/downloads"
    links.mkdir(parents=True)
    marker = links / "manifest.json"
    marker.write_text('{"build":"live-r4"}')
    module.__file__ = str(fake_repo / "scripts/publish-local-installers.py")
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: "10443D1F443D094C\n")
    packages = tmp_path / "packages"
    for kind, product in [("worker", "HeteroES Worker"), ("server", "HeteroES Lab Server")]:
        root = packages / kind
        unpacked = root / "linux-unpacked"
        unpacked.mkdir(parents=True)
        (root / f"{product} Setup 0.1.0.exe").write_bytes(b"synthetic-windows-installer")
        (unpacked / f"heteroes-{kind}").write_bytes(b"synthetic-linux-executable")
        (unpacked / "data").write_bytes(b"payload")
    receipt = tmp_path / "prepared.json"
    cli = packages / "cli"
    cli.mkdir()
    cli_files = {}
    for name, content in [
        ("install-worker.sh", b"#!/bin/sh\n"),
        ("heteroes-worker-linux-test-r5.tar.gz", b"cli-bundle"),
    ]:
        (cli / name).write_bytes(content)
        cli_files[name] = {"sha256": hashlib.sha256(content).hexdigest(), "sizeBytes": len(content)}
    (cli / "linux-worker.json").write_text(json.dumps({"build": "test-r5", "files": cli_files}))
    module.main(["--packages", str(packages), "--build", "test-r5", "--receipt", str(receipt), "--prepare-only"])
    assert marker.read_text() == '{"build":"live-r4"}'
    assert list(links.iterdir()) == [marker]
    report = json.loads(receipt.read_text())
    assert report["publiclyPublished"] is False
    assert report["linuxWorker"]["installer"]["url"] == "/downloads/install-worker.sh"
    assert report["linuxWorker"]["bundle"]["sha256"] == cli_files["heteroes-worker-linux-test-r5.tar.gz"]["sha256"]
    entries = report["installers"] + report["serverInstallers"]
    assert len(entries) == 4
    for entry in entries:
        kind = "worker" if entry["name"].startswith("HeteroES Worker") else "server"
        file = packages / kind / entry["name"]
        assert file.stat().st_size == entry["sizeBytes"]
        assert hashlib.sha256(file.read_bytes()).hexdigest() == entry["sha256"]
        if entry["platform"] == "linux":
            with tarfile.open(file) as archive:
                assert archive.getmember(f"heteroes-{kind}/heteroes-{kind}").mode == 0o755
    published = tmp_path / "published.json"
    module.main(
        [
            "--packages",
            str(packages),
            "--build",
            "test-r5",
            "--receipt",
            str(published),
            "--prepared-receipt",
            str(receipt),
        ]
    )
    assert json.loads(marker.read_text())["build"] == "test-r5"
    assert json.loads(published.read_text())["publiclyPublished"] is True
    assert json.loads(receipt.read_text())["publiclyPublished"] is False
    assert (links / "install-worker.sh").read_bytes() == b"#!/bin/sh\n"
    # Reviewed CLI bytes are checked before any public manifest or link is touched.
    (cli / "install-worker.sh").write_bytes(b"changed-script")
    with pytest.raises(RuntimeError, match="CLI"):
        module.main(
            [
                "--packages",
                str(packages),
                "--build",
                "test-r5",
                "--receipt",
                str(tmp_path / "bad-cli.json"),
                "--prepared-receipt",
                str(receipt),
            ]
        )
    (cli / "install-worker.sh").write_bytes(b"#!/bin/sh\n")
    before = marker.read_bytes()
    entry = entries[0]
    kind = "worker" if entry["name"].startswith("HeteroES Worker") else "server"
    file = packages / kind / entry["name"]
    file.write_bytes(b"x" * file.stat().st_size)
    with pytest.raises(RuntimeError, match="differs"):
        module.main(
            [
                "--packages",
                str(packages),
                "--build",
                "test-r5",
                "--receipt",
                str(tmp_path / "bad.json"),
                "--prepared-receipt",
                str(receipt),
            ]
        )
    assert marker.read_bytes() == before
