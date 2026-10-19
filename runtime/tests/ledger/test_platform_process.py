import json
import os
import subprocess
import sys
import pytest
from heteroes.product.platform_process import identity, acquire_instance_lock, stop_matches, ProcessIdentityUnknown
from heteroes.product import agent


def test_owned_identity_rejects_reused_birth_and_unknown(monkeypatch):
    own = {'pid': os.getpid(), 'birth': identity(os.getpid())}
    assert agent.owned_state(own) is True
    assert agent.owned_state({**own, 'birth': 'other-process'}) is False
    def denied(_): raise ProcessIdentityUnknown('denied')
    monkeypatch.setattr(agent, 'alive', denied)
    assert agent.owned_state(own) is None


def test_lock_blocks_another_process_then_releases(tmp_path):
    path = tmp_path / 'agent.lock'
    lock = acquire_instance_lock(path)
    script = 'from heteroes.product.platform_process import acquire_instance_lock; import sys; acquire_instance_lock(sys.argv[1])'
    assert subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True).returncode != 0
    lock.close()
    assert subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True).returncode == 0


def test_stop_marker_binds_exact_process(tmp_path):
    path = tmp_path / 'stop.json'
    pid = os.getpid(); birth = identity(pid)
    assert not stop_matches(path, pid, birth)
    path.write_text(json.dumps({'pid': pid, 'birth': 'old'}))
    assert not stop_matches(path, pid, birth)
    path.write_text(json.dumps({'pid': pid, 'birth': birth}))
    assert stop_matches(path, pid, birth)
    path.write_text('{broken')
    assert not stop_matches(path, pid, birth)
