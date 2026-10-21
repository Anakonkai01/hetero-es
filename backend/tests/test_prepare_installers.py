"""Preparing reviewable installers must not publish them on the live site."""

import hashlib
import importlib.util
import json
from pathlib import Path
import pytest


def test_prepare_only_builds_hashed_windows_installers_without_touching_public_manifest(tmp_path, monkeypatch):
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
    # desktop apps for Windows only: Linux is the command line Worker (owner decision 2026-10-22)
    assert [e["platform"] for e in entries] == ["windows", "windows"]
    assert not list(packages.rglob("*Linux.tar.gz"))
    for entry in entries:
        kind = "worker" if entry["name"].startswith("HeteroES Worker") else "server"
        file = packages / kind / entry["name"]
        assert file.stat().st_size == entry["sizeBytes"]
        assert hashlib.sha256(file.read_bytes()).hexdigest() == entry["sha256"]
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


def synthetic_build(root, build, cli=True):
    """Packages for one build: two desktop apps and (unless app-only) the CLI script/bundle with its inventory."""
    for kind, product in [("worker", "HeteroES Worker"), ("server", "HeteroES Lab Server")]:
        unpacked = root / kind / "linux-unpacked"
        unpacked.mkdir(parents=True)
        (root / kind / f"{product} Setup 0.1.0.exe").write_bytes(f"windows-{build}".encode())
        (unpacked / f"heteroes-{kind}").write_bytes(b"executable")
    if not cli:
        return root
    files = {}
    (root / "cli").mkdir()
    for name, content in [
        ("install-worker.sh", f"#!/bin/sh\n# {build}\n"),
        (f"heteroes-worker-linux-{build}.tar.gz", build),
    ]:
        (root / "cli" / name).write_bytes(content.encode())
        files[name] = {"sha256": hashlib.sha256(content.encode()).hexdigest(), "sizeBytes": len(content)}
    (root / "cli/linux-worker.json").write_text(json.dumps({"build": build, "files": files}))
    return root


def test_a_refused_publication_leaves_the_previous_one_line_installer_in_place(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / "scripts/publish-local-installers.py"
    spec = importlib.util.spec_from_file_location("publish_installers", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    links = tmp_path / "repo/frontend/public/downloads"
    links.mkdir(parents=True)
    module.__file__ = str(tmp_path / "repo/scripts/publish-local-installers.py")
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: "10443D1F443D094C\n")

    def publish(build, step, cli=True):
        packages = tmp_path / build
        prepared = tmp_path / f"{build}-prepared.json"
        if not prepared.exists():
            synthetic_build(packages, build, cli)
            module.main(["--packages", str(packages), "--build", build, "--receipt", str(prepared), "--prepare-only"])
        argv = ["--packages", str(packages), "--build", build, "--receipt", str(tmp_path / f"{build}-{step}.json")]
        module.main(argv + ["--prepared-receipt", str(prepared)])

    publish("r5", "live")
    alias, manifest = links / "install-worker.sh", links / "manifest.json"
    assert alias.read_text() == "#!/bin/sh\n# r5\n"
    live = manifest.read_bytes()
    # A crashed earlier attempt left a pending alias; a link of the new build already points elsewhere.
    (links / "install-worker.sh.pending").symlink_to(tmp_path / "r5/cli/install-worker.sh")
    (links / "HeteroES Worker-0.1.0-r6-Windows.exe").symlink_to(tmp_path / "r5/cli/install-worker.sh")
    with pytest.raises(RuntimeError, match="another build"):
        publish("r6", "refused")
    assert alias.read_text() == "#!/bin/sh\n# r5\n"
    assert manifest.read_bytes() == live
    assert not (links / "heteroes-worker-linux-r6.tar.gz").exists()
    (links / "HeteroES Worker-0.1.0-r6-Windows.exe").unlink()
    publish("r6", "live")
    assert alias.read_text() == "#!/bin/sh\n# r6\n"
    assert (
        json.loads(manifest.read_text())["linuxWorker"]["installer"]["sha256"]
        == hashlib.sha256(alias.read_bytes()).hexdigest()
    )
    assert not (links / "install-worker.sh.pending").exists()
    # The previous bundle stays downloadable for workers still running the r5 script.
    assert (links / "heteroes-worker-linux-r5.tar.gz").read_text() == "r5"
    # Rolling back to an app-only build must not keep offering a newer build's command line installer.
    publish("r4", "rollback", cli=False)
    assert "linuxWorker" not in json.loads(manifest.read_text())
    assert not alias.exists() and not alias.is_symlink()
