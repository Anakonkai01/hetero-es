from fastapi.testclient import TestClient
from backend.app import create_app
from test_api import Runtime


def test_same_origin_web_keeps_api_auth_and_unknown_paths(tmp_path):
    web = tmp_path/'web'; (web/'assets').mkdir(parents=True)
    (web/'index.html').write_text('<html>Lab UI</html>')
    (web/'assets/app.js').write_text('window.lab=true;')
    (tmp_path/'outside.txt').write_text('private')
    (web/'secret.txt').symlink_to(tmp_path/'outside.txt')
    app = create_app(tmp_path/'state.sqlite', {'admin':'test-admin-pass'}, Runtime(),
                     dispatch=False, web_directory=web)
    with TestClient(app) as client:
        assert 'Lab UI' in client.get('/workspaces/lab').text
        assert client.get('/assets/app.js').text == 'window.lab=true;'
        assert client.get('/assets/missing.js').status_code == 404
        assert client.get('/api/v1/experiments').status_code == 401
        assert client.get('/api/v1/missing').status_code == 404
        assert 'private' not in client.get('/secret.txt').text
        assert client.get('/api/v1/health').status_code == 200
