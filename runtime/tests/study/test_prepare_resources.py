"""Reachability probes and failed signed transfers release their OS handles."""

import os
import socket
from types import SimpleNamespace

import pytest

from heteroes.study import prepare


def test_private_reachability_closes_the_probe_socket(monkeypatch):
    first, second = socket.socketpair()
    monkeypatch.setattr(prepare.socket, "create_connection", lambda *args: first)
    try:
        assert prepare.private_reachable("http://127.0.0.1:1234/object") is True
        assert first.fileno() == -1
    finally:
        first.close()
        second.close()


def test_failed_transfer_closes_the_temporary_file_descriptor(tmp_path, monkeypatch):
    descriptors = []
    original = prepare.tempfile.mkstemp

    def create(*args, **kwargs):
        fd, name = original(*args, **kwargs)
        descriptors.append(fd)
        return fd, name

    def offline(*args, **kwargs):
        raise ConnectionError("injected transfer failure")

    monkeypatch.setattr(prepare.tempfile, "mkstemp", create)
    monkeypatch.setattr(prepare, "opener", lambda **kwargs: SimpleNamespace(open=offline))
    agent = SimpleNamespace(call=lambda *args: {"url": "http://127.0.0.1:1234/transfer"})
    with pytest.raises(ConnectionError):
        prepare.transfer(agent, {"jobId": "j"}, "a" * 64, tmp_path / "data", 100)
    try:
        assert descriptors
        with pytest.raises(OSError):
            os.fstat(descriptors[0])
        assert list(tmp_path.iterdir()) == []
    finally:
        try:
            os.close(descriptors[0])
        except OSError:
            pass
