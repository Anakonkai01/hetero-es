import os
from pathlib import Path
import subprocess
import sys

import pytest
from heteroes.http_transport import BulkUnavailableError, HttpClient


def test_requests_and_replay_keep_public_base_but_weights_use_private_base():
    client = HttpClient('https://control.trycloudflare.com', token='test-grant', bulk_url='http://100.64.0.1:8765')
    observed = []
    class Opener:
        def open(self, request, timeout):
            observed.append(request)
            return object()
    client._opener = Opener()
    assert client._request('GET','/v1/job').full_url == 'https://control.trycloudflare.com/v1/job'
    assert client._request('GET','/v1/updates/'+'a'*64).full_url.startswith('https://control.trycloudflare.com/')
    client.open_stream('/v1/models/'+'a'*64, start=123)
    assert observed[0].full_url == 'http://100.64.0.1:8765/v1/models/'+'a'*64
    assert observed[0].get_header('Authorization') == 'Bearer test-grant'
    assert observed[0].get_header('Range') == 'bytes=123-'


def test_public_endpoint_without_private_bulk_never_downloads_weights():
    with pytest.raises(ValueError, match='bulk'):
        HttpClient('https://control.trycloudflare.com')
    with pytest.raises(ValueError, match='private'):
        HttpClient('https://control.trycloudflare.com', bulk_url='https://other.example.org')


def test_legacy_private_client_keeps_existing_data_path():
    client = HttpClient('http://100.64.0.1:8765', token='test')
    assert client._bulk == 'http://100.64.0.1:8765'


def test_replay_only_client_keeps_control_on_the_public_base_and_refuses_bulk():
    client = HttpClient('https://control.example.org', token='grant', allow_no_bulk=True)
    seen = []
    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            raise AssertionError('no request may be sent for weights')
    client._opener = Opener()
    assert client._request('GET', '/v1/job').full_url == 'https://control.example.org/v1/job'
    assert client._request('GET', '/v1/updates/' + 'a' * 64).full_url.startswith('https://control.example.org/')
    with pytest.raises(BulkUnavailableError, match='private route'):
        client.open_stream('/v1/models/' + 'a' * 64)
    assert seen == []


def test_replay_only_is_not_a_way_to_use_a_public_bulk_url_or_to_weaken_a_private_client():
    with pytest.raises(ValueError, match='private'):
        HttpClient('https://control.example.org', bulk_url='https://other.example.org', allow_no_bulk=True)
    private = HttpClient('http://100.64.0.1:8765', allow_no_bulk=True)
    assert private._bulk == 'http://100.64.0.1:8765'
    with_bulk = HttpClient('https://control.example.org', bulk_url='http://100.64.0.1:8765', allow_no_bulk=True)
    assert with_bulk._bulk == 'http://100.64.0.1:8765'


def test_the_default_still_refuses_a_public_endpoint_without_a_bulk_choice():
    with pytest.raises(ValueError, match='bulk'):
        HttpClient('https://control.example.org', allow_no_bulk=False)


def test_run_worker_refuses_no_bulk_with_a_bulk_url_or_without_replay(tmp_path):
    root = Path(__file__).resolve().parents[1]
    base = [sys.executable, str(root / 'scripts' / 'run_worker.py'), '--model-path', str(tmp_path),
            '--coordinator-url', 'https://compute.example.org', '--worker-id', 'w',
            '--log', str(tmp_path / 'events.jsonl'), '--no-bulk']
    env = dict(os.environ, PYTHONPATH=str(root / 'src'), CUDA_VISIBLE_DEVICES='')
    for extra in (['--bulk-url', 'http://100.64.0.1:8765', '--replay', 'always'], ['--replay', 'never']):
        result = subprocess.run(base + extra, capture_output=True, text=True, env=env, timeout=180)
        assert result.returncode == 2 and '--no-bulk' in result.stdout + result.stderr, result.stderr[-400:]


def test_run_worker_builds_a_replay_only_client_from_its_flag():
    import argparse, importlib.util
    spec = importlib.util.spec_from_file_location('run_worker_script', Path(__file__).resolve().parents[1] / 'scripts' / 'run_worker.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = argparse.Namespace(coordinator_url='https://compute.example.org', token_env='NO_SUCH_TOKEN_VARIABLE',
                              http_timeout_seconds=5.0, bulk_url=None, no_bulk=True)
    assert module.make_client(args)._bulk is None
    args.no_bulk = False
    with pytest.raises(ValueError, match='bulk'):
        module.make_client(args)
