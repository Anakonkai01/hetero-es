from fastapi.testclient import TestClient
from backend.app import create_app
from backend.devices import AgentRuntime


def test_same_origin_web_keeps_api_auth_and_unknown_paths(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>Lab UI</html>")
    (web / "assets/app.js").write_text("window.lab=true;")
    (tmp_path / "outside.txt").write_text("private")
    (web / "secret.txt").symlink_to(tmp_path / "outside.txt")
    app = create_app(
        tmp_path / "state.sqlite", {"admin": "test-admin-pass"}, AgentRuntime(), dispatch=False, web_directory=web
    )
    with TestClient(app) as client:
        assert "Lab UI" in client.get("/workspaces/lab").text
        assert client.get("/assets/app.js").text == "window.lab=true;"
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/api/v1/experiments").status_code == 401
        assert client.get("/api/v1/missing").status_code == 404
        assert "private" not in client.get("/secret.txt").text
        assert client.get("/api/v1/health").status_code == 200


def installer_app(tmp_path, monkeypatch, **extra):
    import json

    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>Lab UI</html>")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "manifest.json").write_text(
        json.dumps(
            {
                "installers": [{"name": "a.exe", "url": "/downloads/a.exe"}],
                "serverInstallers": [{"name": "s.exe", "url": "/downloads/s.exe"}],
                "linuxWorker": {
                    "installer": {"name": "install-worker.sh", "url": "/downloads/install-worker.sh"},
                    "bundle": {"name": "worker.tar.gz", "url": "/downloads/worker.tar.gz"},
                },
            }
        )
    )
    private = tmp_path / "private"
    private.mkdir()
    (private / "config.json").write_text(
        json.dumps(
            {
                "apiUrl": "http://100.64.0.1:8002",
                "bulkApiUrl": "http://100.64.0.1:8002",
                "publicWebUrl": "https://lab.example.org",
                **extra,
            }
        )
    )
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(private))
    return create_app(
        tmp_path / "state.sqlite",
        {"admin": "test-admin-pass"},
        AgentRuntime(),
        dispatch=False,
        web_directory=web,
        downloads_directory=downloads,
    )


def test_installer_links_stay_private_behind_a_public_web_address_by_default(tmp_path, monkeypatch):
    with TestClient(installer_app(tmp_path, monkeypatch)) as client:
        manifest = client.get("/downloads/manifest.json").json()
    assert manifest["privateTransferRequired"] is True
    assert manifest["installers"][0]["url"] == "http://100.64.0.1:8002/downloads/a.exe"
    assert manifest["serverInstallers"][0]["url"] == "http://100.64.0.1:8002/downloads/s.exe"
    assert manifest["linuxWorker"]["installer"]["url"] == "http://100.64.0.1:8002/downloads/install-worker.sh"
    assert manifest["linuxWorker"]["bundle"]["url"] == "http://100.64.0.1:8002/downloads/worker.tar.gz"


def test_installer_links_use_the_public_origin_when_public_downloads_are_enabled(tmp_path, monkeypatch):
    with TestClient(installer_app(tmp_path, monkeypatch, publicDownloads=True)) as client:
        manifest = client.get("/downloads/manifest.json").json()
    assert "privateTransferRequired" not in manifest
    assert manifest["installers"][0]["url"] == "/downloads/a.exe"
    assert manifest["serverInstallers"][0]["url"] == "/downloads/s.exe"


def test_installers_published_as_symlinks_into_another_disk_are_served_with_ranges(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>Lab UI</html>")
    other_disk = tmp_path / "archive"
    other_disk.mkdir()
    (other_disk / "Worker Setup.exe").write_bytes(b"MZ-installer-bytes-0123456789")
    (tmp_path / "secret.txt").write_text("not an installer")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "Worker Setup.exe").symlink_to(other_disk / "Worker Setup.exe")
    (downloads / "manifest.json").write_text('{"installers":[],"serverInstallers":[]}')
    app = create_app(
        tmp_path / "state.sqlite",
        {"admin": "test-admin-pass"},
        AgentRuntime(),
        dispatch=False,
        web_directory=web,
        downloads_directory=downloads,
    )
    with TestClient(app) as client:
        whole = client.get("/downloads/Worker%20Setup.exe")
        assert whole.status_code == 200 and whole.content == b"MZ-installer-bytes-0123456789"
        part = client.get("/downloads/Worker%20Setup.exe", headers={"Range": "bytes=3-9"})
        assert part.status_code == 206 and part.content == b"installer"[:7]
        for escape in ("/downloads/../secret.txt", "/downloads/%2e%2e/secret.txt", "/downloads/..%2fsecret.txt"):
            assert "not an installer" not in client.get(escape).text
