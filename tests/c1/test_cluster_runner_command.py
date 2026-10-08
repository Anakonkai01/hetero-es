"""`scripts/cluster_runner.py: Cluster.start_coordinator`: the command of the coordinator carries the alpha and sigma of the arguments (default 1e-3 as before)."""
import argparse
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
