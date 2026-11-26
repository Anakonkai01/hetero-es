"""A finished run's large local data goes only once the lab store holds its newest point; the ledger always stays."""

from types import SimpleNamespace

import pytest

from heteroes.product import run_cleanup
from heteroes.product.cloud_sync import CloudSync
from heteroes.product.files import read_json, write_json

NOW = 1_000_000.0
LONG_AGO = NOW - run_cleanup.GRACE_SECONDS - 1


def finished_run(tmp_path, status="COMPLETED", ended=LONG_AGO, points=((10, False, "READY"), (12, True, "READY"))):
    root = tmp_path / "runs" / "run"
    large = tmp_path / "large" / "run"
    write_json(root / "large-data.json", {"directory": str(large), "volumeUUID": None})
    write_json(root / "state.json", {"status": status, "updatedAt": ended})
    write_json(root / "assignment.json", {"assignmentId": "a" * 32, "epoch": 1, "config": {}})
    (root / "ledger.sqlite").write_bytes(b"ledger")
    (root / "events.jsonl").write_text("{}\n")
    for name in ("weights", "selection"):
        (large / name).mkdir(parents=True)
        (large / name / "w.bin").write_bytes(b"x" * 100)
    (large / "export").mkdir()
    (large / "export" / "model.safetensors").write_bytes(b"m" * 10)
    for generation, final, cloud in points:
        point = large / "recovery-points" / f"p{generation}{'f' if final else ''}"
        write_json(
            point / "manifest.json",
            {
                "pointId": point.name,
                "generation": generation,
                "final": final,
                "files": {"weights/w.bin": {"sha256": "ab" * 32}},
                "backupPolicy": {"retain": 3},
            },
        )
        (point / "w.bin").write_bytes(b"y" * 50)
        if cloud:
            write_json(point / "cloud-state.json", {"status": cloud, "remoteCreated": True})
    return root, large


def test_a_finished_run_with_its_newest_point_verified_is_cleaned_and_keeps_its_records(tmp_path):
    root, large = finished_run(tmp_path)
    removable = sum(
        f.stat().st_size
        for d in ("weights", "selection", "recovery-points")
        for f in (large / d).rglob("*")
        if f.is_file()
    )
    decided = run_cleanup.apply(root, now=NOW)
    assert decided["removed"] and decided["bytes"] == removable > 300  # weights + selection + both local points
    assert sorted(p.name for p in large.iterdir()) == ["export"]
    assert (root / "ledger.sqlite").read_bytes() == b"ledger" and (root / "events.jsonl").exists()
    receipt = read_json(root / "local-cleanup.json")
    assert receipt["state"] == "done" and receipt["freedBytes"] == removable
    assert receipt["labPoint"]["pointId"] == "p12f" and receipt["labPoint"]["final"]
    assert run_cleanup.plan(root, now=NOW)["reason"] == "already cleaned"


@pytest.mark.parametrize("status", ["RUNNING", "PAUSED", "PREPARING", None])
def test_a_run_that_is_not_over_is_never_cleaned(tmp_path, status):
    root, large = finished_run(tmp_path, status=status)
    assert not run_cleanup.apply(root, now=NOW).get("removed")
    assert (large / "weights" / "w.bin").exists()


def test_a_run_that_just_ended_waits_for_the_grace_period(tmp_path):
    root, large = finished_run(tmp_path, ended=NOW - 60)
    assert run_cleanup.plan(root, now=NOW)["reason"].startswith("ended less than")
    assert run_cleanup.plan(root, now=NOW + run_cleanup.GRACE_SECONDS)["eligible"]


@pytest.mark.parametrize("cloud", [None, "VERIFYING", "PENDING", "ERROR"])
def test_the_newest_point_must_be_verified_by_the_lab_store(tmp_path, cloud):
    # an older READY point is not enough: the newest weights would exist only on this machine
    root, large = finished_run(tmp_path, points=((10, False, "READY"), (12, True, cloud)))
    decided = run_cleanup.apply(root, now=NOW)
    assert not decided["eligible"] and "not verified by the lab store" in decided["reason"]
    assert (large / "recovery-points" / "p12f" / "w.bin").exists() and (large / "weights").exists()


def test_a_final_point_outranks_a_plain_point_of_the_same_generation(tmp_path):
    root, _ = finished_run(tmp_path, points=((12, False, "READY"), (12, True, "PENDING")))
    assert not run_cleanup.plan(root, now=NOW)["eligible"]


def test_a_run_without_any_recovery_point_keeps_its_weights(tmp_path):
    root, large = finished_run(tmp_path, status="FAILED", points=())
    assert run_cleanup.plan(root, now=NOW)["reason"] == "no recovery point on this machine"
    assert (large / "weights").exists()


@pytest.mark.parametrize("status", ["CANCELLED", "FAILED"])
def test_cancelled_and_failed_runs_are_cleaned_like_completed_ones(tmp_path, status):
    root, large = finished_run(tmp_path, status=status, points=((20, False, "READY"),))
    assert run_cleanup.apply(root, now=NOW)["removed"]
    assert not (large / "weights").exists()


def test_an_interrupted_cleanup_is_finished_from_its_receipt(tmp_path):
    root, large = finished_run(tmp_path)
    decided = run_cleanup.plan(root, now=NOW)
    write_json(root / "local-cleanup.json", {"state": "removing", "remove": [str(p) for p in decided["remove"]]})
    # the newest point already went before the interruption: the receipt, not a fresh judgement, decides
    import shutil

    shutil.rmtree(large / "recovery-points" / "p12f")
    assert run_cleanup.apply(root, now=NOW)["removed"]
    assert sorted(p.name for p in large.iterdir()) == ["export"]
    assert read_json(root / "local-cleanup.json")["state"] == "done"


def test_an_unavailable_large_data_volume_is_reported_not_raised(tmp_path):
    root, _ = finished_run(tmp_path)
    write_json(root / "large-data.json", {"directory": "relative/path", "volumeUUID": None})
    assert "unavailable" in run_cleanup.plan(root, now=NOW)["reason"]


def test_the_sync_cycle_cleans_finished_runs_unless_kept(tmp_path, monkeypatch):
    root, large = finished_run(tmp_path)
    agent = SimpleNamespace(
        root=tmp_path, manager=SimpleNamespace(root=tmp_path / "runs"), call=lambda *a, **k: {"status": "READY"}
    )
    monkeypatch.setenv(run_cleanup.KEEP_ENV, "1")
    CloudSync(agent, clock=lambda: NOW).cycle()
    assert (large / "weights").exists()
    monkeypatch.delenv(run_cleanup.KEEP_ENV)
    CloudSync(agent, clock=lambda: NOW).cycle()
    assert not (large / "weights").exists() and (root / "ledger.sqlite").exists()


def test_a_cleanup_error_does_not_stop_the_sync_of_other_runs(tmp_path, monkeypatch):
    finished_run(tmp_path)

    def broken(root, now=None):
        raise RuntimeError("broken receipt")

    monkeypatch.setattr(run_cleanup, "apply", broken)
    agent = SimpleNamespace(
        root=tmp_path, manager=SimpleNamespace(root=tmp_path / "runs"), call=lambda *a, **k: {"status": "READY"}
    )
    CloudSync(agent, clock=lambda: NOW).cycle()
    assert read_json(tmp_path / "runs" / "run" / "local-cleanup-error.json")["errorType"] == "RuntimeError"


def test_freed_bytes_count_a_linked_file_once_and_only_when_all_its_links_go(tmp_path):
    root, large = finished_run(tmp_path)
    import os

    # the newest point links the run's weight file (as recovery points do); a worker cache outside links another one
    os.link(large / "weights" / "w.bin", large / "recovery-points" / "p12f" / "linked.bin")
    (tmp_path / "cache").mkdir()
    os.link(large / "selection" / "w.bin", tmp_path / "cache" / "kept.bin")
    decided = run_cleanup.plan(root, now=NOW)
    files = [f for d in ("weights", "recovery-points") for f in (large / d).rglob("*") if f.is_file()]
    unique = {(f.stat().st_ino): f.stat().st_size for f in files}
    assert decided["bytes"] == sum(unique.values())  # selection/w.bin stays reachable from the cache: not freed
    run_cleanup.apply(root, now=NOW)
    assert (tmp_path / "cache" / "kept.bin").read_bytes() == b"x" * 100
