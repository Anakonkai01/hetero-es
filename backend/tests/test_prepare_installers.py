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
    module.main(["--packages", str(packages), "--build", "test-r5", "--receipt", str(receipt), "--prepare-only"])
    assert marker.read_text() == '{"build":"live-r4"}'
    assert list(links.iterdir()) == [marker]
    report = json.loads(receipt.read_text())
    assert report["publiclyPublished"] is False
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
