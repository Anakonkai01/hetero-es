import hashlib
import json
from pathlib import Path
import sqlite3
import pytest
from heteroes.product.recovery import capture_point, restore_point, publish_new_directory


def sample(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    (root / "weights").mkdir()
    payload = b"canonical toy checkpoint"
    sha = hashlib.sha256(payload).hexdigest()
    (root / "weights" / f"{sha}.bin").write_bytes(payload)
    (root / "config.json").write_text(json.dumps({"runId": "a" * 32, "maxGenerations": 2}))
    with sqlite3.connect(root / "ledger.sqlite") as db:
        db.execute(
            "CREATE TABLE generation_update(generation INTEGER,child_weights_sha256 TEXT,parent_weights_sha256 TEXT,applied_at REAL)"
        )
        db.execute("INSERT INTO generation_update VALUES (0,?,?,1)", (sha, sha))
    return root, sha


def test_snapshot_is_self_contained_and_restores_without_source(tmp_path):
    root, sha = sample(tmp_path)
    point = capture_point(
        root,
        {"generation": 0, "child_sha256": sha, "parent_sha256": sha},
        {"hash": "recipe"},
        {"interval": 1, "retain": 3},
    )
    assert point.is_dir()
    # Capture retains immutable bytes even after canonical file pruning.
    (root / "weights" / f"{sha}.bin").unlink()
    restored = restore_point(point, tmp_path / "restored")
    assert (restored / "weights" / f"{sha}.bin").read_bytes() == b"canonical toy checkpoint"
    assert not (restored / "process.json").exists()
    assert (restored / "dispatch-held.flag").exists()
    with pytest.raises(FileExistsError):
        restore_point(point, tmp_path / "restored")


def test_corruption_and_pending_publication_cannot_restore(tmp_path):
    root, sha = sample(tmp_path)
    point = capture_point(
        root, {"generation": 0, "child_sha256": sha, "parent_sha256": sha}, {}, {"interval": 1, "retain": 3}
    )
    (point / "ledger.sqlite").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        restore_point(point, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_backup_policy_does_not_create_points_between_intervals(tmp_path):
    root, sha = sample(tmp_path)
    assert (
        capture_point(
            root, {"generation": 0, "child_sha256": sha, "parent_sha256": sha}, {}, {"interval": 2, "retain": 3}
        )
        is None
    )
    assert capture_point(
        root, {"generation": 0, "child_sha256": sha, "parent_sha256": sha}, {}, {"interval": 2, "retain": 3}, final=True
    )


def test_restore_publication_refuses_an_empty_competing_destination(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "verified").write_text("ready")
    destination = tmp_path / "destination"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        publish_new_directory(staging, destination)
    assert not list(destination.iterdir()) and (staging / "verified").exists()


def test_ntfs_unsupported_rename_publishes_manifest_last_and_refuses_existing(tmp_path, monkeypatch):
    import ctypes
    import errno
    from types import SimpleNamespace

    def unsupported(*args):
        ctypes.set_errno(errno.EINVAL)
        return -1

    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: SimpleNamespace(renameat2=unsupported))
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "weights").mkdir()
    (staging / "weights" / "model.bin").write_bytes(b"verified")
    (staging / "manifest.json").write_text("published")
    destination = tmp_path / "destination"
    import heteroes.product.recovery as recovery

    original = recovery.os.link
    observed = []

    def link(source, target):
        observed.append(Path(source).name)
        return original(source, target)

    monkeypatch.setattr(recovery.os, "link", link)
    publish_new_directory(staging, destination)
    assert observed[-1] == "manifest.json"
    assert (destination / "weights" / "model.bin").read_bytes() == b"verified" and not staging.exists()
    staging.mkdir()
    (staging / "manifest.json").write_text("second")
    with pytest.raises(FileExistsError):
        publish_new_directory(staging, destination)
    assert (destination / "manifest.json").read_text() == "published"


def test_ledger_ahead_of_selected_weights_is_rejected(tmp_path):
    root, sha = sample(tmp_path)
    point = capture_point(
        root, {"generation": 0, "child_sha256": sha, "parent_sha256": sha}, {}, {"interval": 1, "retain": 3}
    )
    with sqlite3.connect(point / "ledger.sqlite") as db:
        db.execute("INSERT INTO generation_update VALUES (1,?,?,2)", (sha, sha))
    manifest = json.loads((point / "manifest.json").read_text())
    manifest["files"]["ledger.sqlite"]["sha256"] = hashlib.sha256((point / "ledger.sqlite").read_bytes()).hexdigest()
    manifest["files"]["ledger.sqlite"]["sizeBytes"] = (point / "ledger.sqlite").stat().st_size
    (point / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="ahead"):
        restore_point(point, tmp_path / "bad")


def test_optional_policy_corruption_and_write_failure_do_not_interrupt_compute(tmp_path, monkeypatch):
    from heteroes.product import runner

    current = {"interval": 1, "retain": 3}
    logs = []
    (tmp_path / "backup-policy.json").write_text("broken JSON")
    assert runner.apply_backup_policy(tmp_path, 0, current, logs.append) == current
    requested = {"interval": 2, "retain": 7}
    (tmp_path / "backup-policy.json").write_text(json.dumps(requested))

    def denied(*args):
        raise PermissionError("Optional policy history is read-only")

    monkeypatch.setattr(runner, "write_json", denied)
    assert runner.apply_backup_policy(tmp_path, 1, current, logs.append) == requested
    assert any(e["event"] == "backup_policy_error" for e in logs)


def test_source_identity_pins_runtime_bytes_without_a_git_checkout(tmp_path):
    from heteroes.product.recovery import source_identity

    source = tmp_path / "runtime.py"
    source.write_bytes(b"first numerical implementation")
    first = source_identity(tmp_path)
    assert first["sourceFiles"]["runtime.py"] == hashlib.sha256(source.read_bytes()).hexdigest()
    (tmp_path / "unrelated.log").write_text("not code")
    assert source_identity(tmp_path) == first
    source.write_bytes(b"changed numerical implementation")
    assert source_identity(tmp_path)["sourceTreeSha256"] != first["sourceTreeSha256"]
