import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.app import app_from_environment
from backend.server import initialize


def test_fresh_bootstrap_holds_queue_and_keeps_only_password_hash(tmp_path, monkeypatch):
    root = tmp_path/'lab'
    password = 'a-unique-test-admin-password'
    result = initialize(root, {'username':'labowner','password':password,'host':'127.0.0.1',
        'port':8765,'storageDirectory':str(tmp_path/'artifacts')})
    assert result['dispatchHeld'] is True
    assert json.loads((root/'credentials.json').read_text()) == {'users':{}}
    assert password not in (root/'config.json').read_text()
    with sqlite3.connect(root/'state/product.sqlite') as db:
        digest = db.execute('SELECT hash FROM users').fetchone()[0]
        assert digest.startswith('$argon2') and password not in digest
    monkeypatch.setenv('HETEROES_PRIVATE_CONFIG',str(root))
    app = app_from_environment()
    with TestClient(app) as client:
        response=client.post('/api/v1/auth/login',json={'username':'labowner','password':password})
        assert response.status_code == 200
        assert response.json()['user']['platformAdmin'] is True
    with pytest.raises(FileExistsError):
        initialize(root, {'username':'labowner','password':password,'host':'127.0.0.1',
            'port':8765,'storageDirectory':str(tmp_path/'artifacts')})
    assert (root/'state/product.sqlite').is_file()


def test_failed_selected_disk_preflight_does_not_leave_a_partial_lab(tmp_path):
    root=tmp_path/'lab'
    with pytest.raises(ValueError,match='not mounted'):
        initialize(root, {'username':'labowner','password':'test-admin-password',
            'host':'127.0.0.1','port':8765,'storageDirectory':str(tmp_path/'artifacts'),
            'storageVolumeUUID':'00000000-0000-0000-0000-000000000000'})
    assert not root.exists()
    assert not (tmp_path/'artifacts').exists()
