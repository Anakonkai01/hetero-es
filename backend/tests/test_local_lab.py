"""The local-lab manager: named Cloudflare tunnel support, tested with a fake cloudflared."""
import importlib.util
import json
from pathlib import Path
import stat
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'local-lab.py'


@pytest.fixture(scope='module')
def lab_script():
    spec = importlib.util.spec_from_file_location('local_lab_script', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_cloudflared(path, body):
    path.write_text('#!/bin/sh\n' + body + '\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_tunnel_names_depend_on_the_named_tunnel_setting(lab_script):
    assert lab_script.tunnel_names({}) == ['web-quick', 'compute-quick']
    assert lab_script.tunnel_names({'namedTunnelConfig': '/x/named.yml'}) == ['named-tunnel']


def test_named_tunnel_waits_for_the_registration_message(lab_script, tmp_path):
    binary = fake_cloudflared(tmp_path / 'cloudflared', 'echo "INF Registered tunnel connection connIndex=0"; exec sleep 30')
    (tmp_path / 'named.yml').write_text('tunnel: x\n')
    record = lab_script.named(tmp_path, 'named-tunnel', tmp_path / 'named.yml', binary, {})
    try:
        assert lab_script.alive(record)
        assert json.loads((tmp_path / 'named-tunnel-process.json').read_text())['pid'] == record['pid']
    finally:
        lab_script.stop(tmp_path, 'named-tunnel')
    assert not lab_script.alive(record)


def test_named_tunnel_that_exits_or_never_registers_is_an_error(lab_script, tmp_path, monkeypatch):
    (tmp_path / 'named.yml').write_text('tunnel: x\n')
    dies = fake_cloudflared(tmp_path / 'dies', 'echo "ERR credentials missing"; exit 1')
    with pytest.raises(RuntimeError, match='did not register'):
        lab_script.named(tmp_path, 'named-tunnel', tmp_path / 'named.yml', dies, {})
    monkeypatch.setattr(lab_script, 'REGISTRATION_SECONDS', 1)
    silent = fake_cloudflared(tmp_path / 'silent', 'exec sleep 30')
    with pytest.raises(RuntimeError, match='did not register'):
        lab_script.named(tmp_path, 'named-tunnel', tmp_path / 'named.yml', silent, {})
    lab_script.stop(tmp_path, 'named-tunnel')


def test_named_tunnel_needs_fixed_https_addresses_and_a_config_file(lab_script, tmp_path):
    good = {'namedTunnelConfig': str(tmp_path / 'named.yml'),
            'publicWebUrl': 'https://lab.example.org', 'publicComputeUrl': 'https://compute.example.org'}
    (tmp_path / 'named.yml').write_text('tunnel: x\n')
    lab_script.check_named(good)
    for broken in ({**good, 'publicWebUrl': 'http://lab.example.org'},
                   {**good, 'publicWebUrl': 'https://192.168.1.20:8443'},  # private: not a public name
                   {**good, 'publicComputeUrl': None},
                   {**good, 'namedTunnelConfig': str(tmp_path / 'missing.yml')},
                   {**good, 'publicWebUrl': good['publicComputeUrl']}):
        with pytest.raises(ValueError):
            lab_script.check_named(broken)
    lab_script.check_named({})  # no named tunnel configured: nothing to check
