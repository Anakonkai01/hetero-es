"""`scripts/cluster_runner.py: Cluster.start_coordinator`: the command of the coordinator carries the alpha and sigma of the arguments (default 1e-3 as before)."""
import argparse

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import cluster_runner as cr  # noqa: E402


def command_for(tmp_path, monkeypatch, argv):
    parser = argparse.ArgumentParser()
    cr.add_cluster_arguments(parser)
    args = parser.parse_args(argv)
    args.coordinator_noise_threads = None
    seen = {}

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeProcess()

    monkeypatch.setattr(cr.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cr, "wait_health", lambda url, seconds: None)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cluster = cr.Cluster(args, "t", run_dir)
    cluster.start_coordinator("greedy", [], 8, 2)
    return seen["cmd"]


def value_after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_alpha_and_sigma_default_to_one_thousandth(tmp_path, monkeypatch):
    cmd = command_for(tmp_path, monkeypatch, ["--scratch-dir", str(tmp_path / "s")])

    assert float(value_after(cmd, "--alpha")) == 1e-3 and float(value_after(cmd, "--sigma")) == 1e-3


def test_alpha_and_sigma_of_the_arguments_reach_the_coordinator(tmp_path, monkeypatch):
    cmd = command_for(tmp_path, monkeypatch, ["--scratch-dir", str(tmp_path / "s"), "--alpha", "2.5e-3", "--sigma", "3e-4"])

    assert float(value_after(cmd, "--alpha")) == 2.5e-3 and float(value_after(cmd, "--sigma")) == 3e-4


def remote_command(tmp_path, monkeypatch, argv):
    parser = argparse.ArgumentParser()
    cr.add_cluster_arguments(parser)
    args = parser.parse_args(["--scratch-dir", str(tmp_path / "s")] + argv)
    seen = []

    class FakeProcess:
        pass

    monkeypatch.setattr(cr.subprocess, "Popen", lambda cmd, **kwargs: seen.append(cmd) or FakeProcess())
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cluster = cr.Cluster(args, "t", run_dir)
    cluster.start_worker(cr.SLOW, 16)
    cluster.start_worker(cr.FAST, 16)
    return seen[0][-1], seen[1]               # the remote shell command, the local command


def test_the_remote_worker_downloads_by_default(tmp_path, monkeypatch):
    remote, local = remote_command(tmp_path, monkeypatch, [])

    assert "--replay" not in remote and "--replay" not in local


def test_replay_options_reach_the_remote_worker_only(tmp_path, monkeypatch):
    remote, local = remote_command(tmp_path, monkeypatch, ["--replay", "auto", "--replay-profile", "/tmp/p.json", "--replay-verify-every", "3"])

    assert "--replay auto --replay-verify-every 3 --profile /tmp/p.json" in remote
    assert "--replay" not in local


def third_commands(tmp_path, monkeypatch, argv):
    parser = argparse.ArgumentParser()
    cr.add_cluster_arguments(parser)
    args = parser.parse_args(["--scratch-dir", str(tmp_path / "s")] + argv)
    seen = []

    class FakeProcess:
        pass

    monkeypatch.setattr(cr.subprocess, "Popen", lambda cmd, **kwargs: seen.append(cmd) or FakeProcess())
    monkeypatch.setattr(cr, "wait_health", lambda url, seconds: None)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cluster = cr.Cluster(args, "t", run_dir)
    args.coordinator_noise_threads = None
    cluster.start_coordinator("greedy", [], 8, 2)
    cluster.start_worker(cr.THIRD, 64)
    cluster.start_worker(cr.SLOW, 64)
    return seen, cluster


def test_the_third_worker_runs_on_its_own_machine_with_its_own_address_of_the_coordinator(tmp_path, monkeypatch):
    seen, cluster = third_commands(tmp_path, monkeypatch, ["--third", "me@100.1.2.3", "--third-url", "http://100.9.9.9:8765", "--host", "10.10.10.1"])
    third, slow = seen[1], seen[2]

    assert third[:3] == ["ssh", "-o", "ServerAliveInterval=15"] and third[3] == "me@100.1.2.3"
    assert "--coordinator-url http://100.9.9.9:8765" in third[-1] and "--worker-id worker-3060" in third[-1] and "PYTHONPATH=src" in third[-1]
    assert "~/heteroes-venv/bin/python" in third[-1] and "/tmp/bench-t-worker-3060" in third[-1]
    assert slow[3] == cr.DEFAULTS["remote"] and "--coordinator-url http://10.10.10.1:8765" in slow[-1] and "PYTHONPATH" not in slow[-1]
    assert "/tmp/bench-t " not in slow[-1] and "/tmp/bench-t/" in slow[-1]                      # the 1660S keeps the old directory name
    assert {r["worker"]: r["target"] for r in cluster.remotes} == {cr.THIRD: "me@100.1.2.3", cr.SLOW: cr.DEFAULTS["remote"]}


def test_the_third_worker_needs_the_third_option(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="--third"):
        third_commands(tmp_path, monkeypatch, [])


def test_replay_of_the_third_worker_is_its_own_option(tmp_path, monkeypatch):
    seen, _ = third_commands(tmp_path, monkeypatch, ["--third", "me@x", "--third-replay", "auto", "--third-replay-profile", "/tmp/p3.json", "--replay", "always"])

    assert "--replay auto" in seen[1][-1] and "--profile /tmp/p3.json" in seen[1][-1]
    assert "--replay always" in seen[2][-1] and "/tmp/p3.json" not in seen[2][-1]


def test_the_coordinator_listens_where_bind_host_says(tmp_path, monkeypatch):
    seen, _ = third_commands(tmp_path, monkeypatch, ["--third", "me@x", "--host", "10.10.10.1", "--bind-host", "0.0.0.0"])
    assert value_after(seen[0], "--host") == "0.0.0.0"
    (tmp_path / "b").mkdir()
    seen, _ = third_commands(tmp_path / "b", monkeypatch, ["--third", "me@x", "--host", "10.10.10.1"])
    assert value_after(seen[0], "--host") == "10.10.10.1"


def test_the_logs_are_collected_and_cleaned_on_the_machine_of_each_remote_worker(tmp_path, monkeypatch):
    _, cluster = third_commands(tmp_path, monkeypatch, ["--third", "me@x"])
    calls = []
    monkeypatch.setattr(cr.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))
    cluster.processes = {}
    cluster.collect_and_clean([cr.SLOW, cr.THIRD])

    copies = {c[2].split(":")[0]: c[2].split(":")[1] for c in calls if c[0] == "scp"}
    assert copies == {"me@x": "/tmp/bench-t-worker-3060/worker-3060.jsonl", cr.DEFAULTS["remote"]: "/tmp/bench-t/worker-1660s.jsonl"}
    assert {c[1] for c in calls if c[0] == "ssh"} == {"me@x", cr.DEFAULTS["remote"]}
