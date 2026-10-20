"""Native Windows must not inspect WSL libraries; known failed launches must not retain fictitious GPU ownership."""

import os
from types import SimpleNamespace

import pytest

from heteroes.product import remote
from heteroes.product.platform_process import ProcessIdentityUnknown
from test_device_agent import agent, start_command


def test_native_windows_never_inspects_wsl_paths_even_when_the_working_directory_is_on_wsl(monkeypatch):
    class InaccessibleWSL:
        def __truediv__(self, name):
            raise PermissionError("UNC-mounted WSL driver directory")

    monkeypatch.setattr(remote.sys, "platform", "win32")
    monkeypatch.setenv("PATH", r"C:\Windows\System32;C:\Tools")
    monkeypatch.setenv("LD_LIBRARY_PATH", "preserved-existing-value")
    result = remote.worker_environment("native-source", "fixture-token", InaccessibleWSL())
    assert result["PATH"] == r"C:\Windows\System32;C:\Tools"
    assert result["LD_LIBRARY_PATH"] == "preserved-existing-value"
    assert result["PYTHONPATH"] == "native-source"


@pytest.mark.parametrize("stage", ["environment", "spawn"])
def test_a_known_failure_before_process_creation_can_be_retried_and_releases_ownership(tmp_path, monkeypatch, stage):
    device = agent(tmp_path)
    device.enabled = True
    command = start_command()

    def denied(*args, **kwargs):
        raise PermissionError("known pre-spawn failure")

    if stage == "environment":
        monkeypatch.setattr(remote, "worker_environment", denied)
        monkeypatch.setattr(remote.subprocess, "Popen", lambda *a, **k: pytest.fail("spawn must not run"))
    else:
        monkeypatch.setattr(remote.subprocess, "Popen", denied)
    for _ in range(2):
        with pytest.raises(PermissionError):
            device.handle(command)
        directory = device.worker_directory(command)
        assert not (directory / "launch-intent.json").exists()
        assert not (directory / "process.json").exists()
        assert device._worker(command, "poll")["alive"] is False


def test_failure_after_process_creation_preserves_unknown_ownership_and_forbids_a_second_spawn(tmp_path, monkeypatch):
    device = agent(tmp_path)
    device.enabled = True
    command = start_command()
    spawned = []

    def spawn(*args, **kwargs):
        spawned.append(args)
        return SimpleNamespace(pid=12345)

    def unknown(pid):
        raise ProcessIdentityUnknown("birth cannot be queried after creation")

    monkeypatch.setattr(remote.subprocess, "Popen", spawn)
    monkeypatch.setattr(remote, "identity", unknown)
    with pytest.raises(ProcessIdentityUnknown):
        device.handle(command)
    assert (device.worker_directory(command) / "launch-intent.json").exists()
    assert device._worker(command, "poll")["alive"] is None
    with pytest.raises(RuntimeError, match="launch ownership"):
        device.handle(command)
    assert len(spawned) == 1


def test_successful_launch_records_the_process_and_retries_adopt_it(tmp_path, monkeypatch):
    device = agent(tmp_path)
    device.enabled = True
    command = start_command()
    spawned = []

    def spawn(*args, **kwargs):
        directory = device.worker_directory(command)
        assert (directory / "launch-intent.json").exists()  # durable intent precedes the OS call
        spawned.append(args)
        return SimpleNamespace(pid=os.getpid())

    monkeypatch.setattr(remote.subprocess, "Popen", spawn)
    device.handle(command)
    assert (device.worker_directory(command) / "process.json").exists()
    assert device._worker(command, "start")["alive"] is True
    assert len(spawned) == 1
