"""The local-lab manager: named Cloudflare tunnel support, tested with a fake cloudflared."""

import importlib.util
import json
from pathlib import Path
import stat
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "local-lab.py"


@pytest.fixture(scope="module")
def lab_script():
    spec = importlib.util.spec_from_file_location("local_lab_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_cloudflared(path, body):
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_tunnel_names_depend_on_the_named_tunnel_setting(lab_script):
    assert lab_script.tunnel_names({}) == ["web-quick", "compute-quick"]
    assert lab_script.tunnel_names({"namedTunnelConfig": "/x/named.yml"}) == ["named-tunnel"]


def test_named_tunnel_waits_for_the_registration_message(lab_script, tmp_path):
    binary = fake_cloudflared(
        tmp_path / "cloudflared", 'echo "INF Registered tunnel connection connIndex=0"; exec sleep 30'
    )
    (tmp_path / "named.yml").write_text("tunnel: x\n")
    record = lab_script.named(tmp_path, "named-tunnel", tmp_path / "named.yml", binary, {})
    try:
        assert lab_script.alive(record)
        assert json.loads((tmp_path / "named-tunnel-process.json").read_text())["pid"] == record["pid"]
    finally:
        lab_script.stop(tmp_path, "named-tunnel")
    assert not lab_script.alive(record)


def test_named_tunnel_that_exits_or_never_registers_is_an_error(lab_script, tmp_path, monkeypatch):
    (tmp_path / "named.yml").write_text("tunnel: x\n")
    dies = fake_cloudflared(tmp_path / "dies", 'echo "ERR credentials missing"; exit 1')
    with pytest.raises(RuntimeError, match="did not register"):
        lab_script.named(tmp_path, "named-tunnel", tmp_path / "named.yml", dies, {})
    monkeypatch.setattr(lab_script, "REGISTRATION_SECONDS", 1)
    silent = fake_cloudflared(tmp_path / "silent", "exec sleep 30")
    with pytest.raises(RuntimeError, match="did not register"):
        lab_script.named(tmp_path, "named-tunnel", tmp_path / "named.yml", silent, {})
    lab_script.stop(tmp_path, "named-tunnel")


def test_named_tunnel_needs_fixed_https_addresses_and_a_config_file(lab_script, tmp_path):
    good = {
        "namedTunnelConfig": str(tmp_path / "named.yml"),
        "publicWebUrl": "https://lab.example.org",
        "publicComputeUrl": "https://compute.example.org",
    }
    (tmp_path / "named.yml").write_text("tunnel: x\n")
    lab_script.check_named(good)
    for broken in (
        {**good, "publicWebUrl": "http://lab.example.org"},
        {**good, "publicWebUrl": "https://192.168.1.20:8443"},  # private: not a public name
        {**good, "publicComputeUrl": None},
        {**good, "namedTunnelConfig": str(tmp_path / "missing.yml")},
        {**good, "publicWebUrl": good["publicComputeUrl"]},
    ):
        with pytest.raises(ValueError):
            lab_script.check_named(broken)
    lab_script.check_named({})  # no named tunnel configured: nothing to check


# --- holding the queue while the services restart ---------------------------------------------


@pytest.fixture
def lab_db(tmp_path):
    from backend.server import initialize

    root = tmp_path / "lab"
    initialize(
        root,
        {
            "username": "admin",
            "password": "test-password-long",
            "host": "127.0.0.1",
            "port": 8002,
            "storageDirectory": str(tmp_path / "objects"),
        },
    )
    return root / "state" / "product.sqlite"


def add_run(db_path, status):
    import sqlite3

    with sqlite3.connect(db_path) as db:
        db.execute(
            "INSERT INTO experiments VALUES (?,?,?,NULL)", (status + "-run", "admin", json.dumps({"status": status}))
        )


def add_reservation(db_path):
    import sqlite3

    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO physical_reservations VALUES ('GPU-1', ?)", ("a" * 32,))


def test_lab_state_reports_the_hold_and_whether_a_run_or_reservation_is_live(lab_script, lab_db):
    assert lab_script.lab_state(lab_db) == {"held": True, "busy": False}
    lab_script.set_hold(lab_db, False)
    assert lab_script.lab_state(lab_db) == {"held": False, "busy": False}
    for status in ("COMPLETED", "FAILED", "CANCELLED", "DRAFT", "QUEUED", "PAUSED"):
        add_run(lab_db, status)
    assert lab_script.lab_state(lab_db)["busy"] is False  # nothing is executing
    add_run(lab_db, "RUNNING")
    assert lab_script.lab_state(lab_db)["busy"] is True


@pytest.mark.parametrize("status", ["STARTING", "RUNNING", "CANCELLING", "RECOVERING", "DRAINING", "PAUSING"])
def test_every_executing_status_counts_as_busy(lab_script, lab_db, status):
    add_run(lab_db, status)
    assert lab_script.lab_state(lab_db)["busy"] is True


def test_a_physical_reservation_counts_as_busy(lab_script, lab_db):
    add_reservation(lab_db)
    assert lab_script.lab_state(lab_db)["busy"] is True


def test_an_open_idle_queue_is_held_during_the_action_and_reopened_after(lab_script, lab_db):
    lab_script.set_hold(lab_db, False)
    with lab_script.held_while_idle(lab_db) as plan:
        assert lab_script.lab_state(lab_db)["held"] is True
        assert plan["reopen"] is True
    assert lab_script.lab_state(lab_db)["held"] is False


def test_an_already_held_queue_stays_held(lab_script, lab_db):
    with lab_script.held_while_idle(lab_db) as plan:
        assert plan["reopen"] is False
    assert lab_script.lab_state(lab_db)["held"] is True


def test_a_failing_action_still_restores_the_queue(lab_script, lab_db):
    lab_script.set_hold(lab_db, False)
    with pytest.raises(RuntimeError, match="boom"):
        with lab_script.held_while_idle(lab_db):
            raise RuntimeError("boom")
    assert lab_script.lab_state(lab_db)["held"] is False


def test_a_busy_lab_refuses_a_restart_and_stays_as_it_was(lab_script, lab_db):
    lab_script.set_hold(lab_db, False)
    add_run(lab_db, "RUNNING")
    with pytest.raises(RuntimeError, match="active"):
        with lab_script.held_while_idle(lab_db):
            pytest.fail("the action must not run")
    assert lab_script.lab_state(lab_db)["held"] is False


def test_booting_a_busy_lab_leaves_the_queue_held_for_an_administrator(lab_script, lab_db):
    lab_script.set_hold(lab_db, False)
    add_reservation(lab_db)
    with lab_script.held_while_idle(lab_db, allow_busy=True) as plan:
        assert plan["reopen"] is False and plan["busy"] is True
    assert lab_script.lab_state(lab_db)["held"] is True


def test_a_missing_storage_disk_is_named_instead_of_failing_later_in_a_private_log(lab_script, tmp_path):
    config = {"storageDirectory": str(tmp_path / "lab-storage"), "storageVolumeUUID": "10443D1F443D094C"}
    with pytest.raises(RuntimeError, match=r"10443D1F443D094C.*not mounted.*retry"):
        lab_script.check_storage(config, probe=lambda directory: "")
    with pytest.raises(RuntimeError, match="not mounted"):
        lab_script.check_storage(config, probe=lambda directory: "a22ef996-a5b5-47c8-b220-428e8813dfb3")
    lab_script.check_storage(config, probe=lambda directory: "10443D1F443D094C")


def test_storage_without_a_pinned_disk_is_not_probed(lab_script):
    def probe(directory):
        raise AssertionError("nothing to check")

    lab_script.check_storage({}, probe=probe)
    lab_script.check_storage({"storageDirectory": "/somewhere"}, probe=probe)


def test_a_restart_checks_the_disk_before_it_stops_anything(lab_script, monkeypatch, tmp_path):
    stopped = []
    monkeypatch.setattr(lab_script, "stop", lambda root, name: stopped.append(name))
    monkeypatch.setattr(lab_script, "mounted_uuid", lambda directory: "")
    args = type("Args", (), {"action": "restart", "private": tmp_path})()
    config = {"storageDirectory": str(tmp_path / "s"), "storageVolumeUUID": "DISK"}
    with pytest.raises(RuntimeError, match="not mounted"):
        lab_script.operate(args, tmp_path, config, {"reopen": False, "busy": False})
    assert stopped == []
