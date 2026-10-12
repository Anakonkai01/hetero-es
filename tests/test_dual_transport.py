import pytest
from heteroes.http_transport import HttpClient


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
