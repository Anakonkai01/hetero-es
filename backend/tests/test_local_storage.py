"""Real disk writes, signed HTTP transfers, immutable CAS and manifest-last."""
import json
import time
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.local_storage import LocalBackend
from backend.cloud_storage import CloudStorage
from backend.devices import AgentRuntime
from backend.store import Store
from test_cloud_storage import manifest


@pytest.fixture
def local(tmp_path):
    backend = LocalBackend(tmp_path/'objects', tmp_path/'private/storage.key', 'http://127.0.0.1:8002')
    runtime = AgentRuntime(backend)
    store = Store(tmp_path/'lab.sqlite', {'admin':'test-admin-pass'}, runtime)
    storage = CloudStorage(store, backend, quota_bytes=1_000_000)
    app = FastAPI(); backend.install_routes(app)
    with TestClient(app) as client:
        yield backend, storage, client


def path(url):
    return urlsplit(url).path


def test_real_upload_verify_download_and_no_cloud_request_caps(local):
    backend, storage, client = local
    m = manifest(); plan = storage.begin(m); entry = plan['objects'][0]
    assert not backend.path('manifests/'+m['pointId']+'.json').exists()
    assert client.put(path(entry['url']), content=b'weights').status_code == 200
    storage.complete_object(m['pointId'], entry['sha256'], [])
    storage.verify(m['pointId'])
    assert json.loads(b''.join(backend.get('manifests/'+m['pointId']+'.json'))) == m
    assert client.get(path(backend.download_url('objects/'+entry['sha256']))).content == b'weights'
    assert storage.usage()['storageMode'] == 'local'
    storage._requests(a=1_000_000_000,b=1_000_000_000)


def test_scoped_url_rejects_tampering_wrong_method_and_expiry(local, monkeypatch):
    backend, _, client = local
    entry = backend.upload_plan('uploads/'+'a'*64+'/'+'b'*32, 7)
    assert client.get(path(entry['url'])).status_code == 403
    assert client.put(path(entry['url'])+'0', content=b'weights').status_code == 403
    monkeypatch.setattr('backend.local_storage.time.time',lambda:time.monotonic()+10**11)
    assert client.put(path(entry['url']), content=b'weights').status_code == 403


def test_wrong_bytes_cannot_publish_and_upload_cannot_be_overwritten(local):
    backend, storage, client = local
    m = manifest(); entry = storage.begin(m)['objects'][0]
    url = path(entry['url'])
    assert client.put(url, content=b'short').status_code == 400
    assert client.put(url, content=b'corrupt').status_code == 200
    assert client.put(url, content=b'weights').status_code == 409
    with pytest.raises(ValueError,match='checksum'):
        storage.verify(m['pointId'])
    assert not backend.path('manifests/'+m['pointId']+'.json').exists()


def test_retry_is_identical_and_signing_key_survives_restart(local, tmp_path):
    backend, _, client = local
    key='uploads/'+'a'*64+'/'+'b'*32
    entry=backend.upload_plan(key,7)
    for _ in range(2):
        assert client.put(path(entry['url']),content=b'weights').status_code==200
    restored=LocalBackend(backend.root,tmp_path/'private/storage.key','http://127.0.0.1:8002')
    token=entry['url'].rsplit('/',1)[1]
    assert restored.grant(token,'PUT')['key']==key


def test_path_traversal_and_symlinks_are_rejected(local, tmp_path):
    backend, _, _ = local
    for key in ['../../secret','objects/../secret','objects/'+'a'*64+'/x','/etc/passwd']:
        with pytest.raises(ValueError): backend.path(key)
    (backend.root/'objects').symlink_to(tmp_path)
    with pytest.raises(ValueError): backend.path('objects/'+'a'*64)
