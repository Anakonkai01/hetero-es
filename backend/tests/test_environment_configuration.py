"""Container settings override private files without exposing secret values or modifying those files."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.core.config import load_config
from backend.apps.factory import app_from_environment


@pytest.fixture(autouse=True)
def configuration_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith("HETEROES_") and not name.startswith("HETEROES_TEST_"):
            monkeypatch.delenv(name)


def test_environment_overrides_private_settings_and_preserves_unrelated_fields(tmp_path, monkeypatch):
    original = {
        "deploymentMode": "agent",
        "authMode": "local",
        "publicWebUrl": "https://old.example.test",
        "custom": {"keep": True},
    }
    private = tmp_path / "private"
    private.mkdir()
    source = private / "config.json"
    source.write_text(json.dumps(original))
    before = source.read_bytes()
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(private))
    monkeypatch.setenv("HETEROES_AUTH_MODE", "oidc")
    monkeypatch.setenv("HETEROES_PUBLIC_URL", "https://new.example.test")
    monkeypatch.setenv("HETEROES_OIDC_ISSUER", "https://identity.example.test/realms/lab")
    monkeypatch.setenv("HETEROES_OIDC_JWKS_URL", "http://identity:8080/realms/lab/protocol/openid-connect/certs")
    result = load_config()
    assert result["authMode"] == "oidc" and result["publicWebUrl"] == "https://new.example.test"
    assert result["oidcIssuer"] == os.environ["HETEROES_OIDC_ISSUER"]
    assert result["oidcJwksUrl"] == os.environ["HETEROES_OIDC_JWKS_URL"]
    assert result["custom"] == original["custom"] and source.read_bytes() == before
    monkeypatch.setenv("HETEROES_PUBLIC_URL", "https://rotated.example.test")
    assert load_config()["publicWebUrl"] == "https://rotated.example.test"


def test_environment_only_defaults_use_an_explicit_private_state_directory_without_writes(tmp_path, monkeypatch):
    state = tmp_path / "new-state"
    monkeypatch.setenv("HETEROES_STATE_DIRECTORY", str(state))
    config = load_config()
    assert config["deploymentMode"] == "agent" and config["productStateDirectory"] == str(state)
    assert Path(config["storageDirectory"]).is_relative_to(state)
    assert Path(config["metadataStorageDirectory"]).is_relative_to(state)
    assert not state.exists()


def test_database_and_object_credentials_can_come_from_secret_files(tmp_path, monkeypatch, capsys):
    db = tmp_path / "database-url"
    db.write_text("postgresql+psycopg://env-user:never-publish-db-secret@127.0.0.1:1/product\n")
    secret = tmp_path / "s3-secret"
    secret.write_text("never-publish-s3-secret\n")
    monkeypatch.setenv("HETEROES_DATABASE_URL_FILE", str(db))
    monkeypatch.setenv("HETEROES_STORAGE_MODE", "s3")
    monkeypatch.setenv("HETEROES_STORAGE_INTERNAL_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("HETEROES_STORAGE_DEVICE_ENDPOINT", "http://100.64.0.10:19000")
    monkeypatch.setenv("HETEROES_STORAGE_ACCESS_KEY_ID", "fixture-access-id")
    monkeypatch.setenv("HETEROES_STORAGE_SECRET_ACCESS_KEY_FILE", str(secret))
    monkeypatch.setenv("HETEROES_STORAGE_RECOVERY_BUCKET", "fixture-recovery")
    monkeypatch.setenv("HETEROES_STORAGE_DATASETS_BUCKET", "fixture-datasets")
    monkeypatch.setenv("HETEROES_STORAGE_BACKUPS_BUCKET", "fixture-backups")
    monkeypatch.setenv("HETEROES_STORAGE_QUOTA_BYTES", "123456")
    monkeypatch.setenv("HETEROES_STORAGE_SIGNING_KEY_FILE", str(tmp_path / "signing.key"))
    config = load_config()
    assert config["databaseUrl"] == db.read_text().strip()
    assert config["s3"]["secretAccessKey"] == secret.read_text().strip()
    assert config["s3"]["accessKeyId"] == "fixture-access-id"
    assert config["s3"]["endpointUrl"] == "http://minio:9000"
    assert config["s3"]["deviceEndpointUrl"] == "http://100.64.0.10:19000"
    assert config["s3"]["buckets"] == {
        "recovery": "fixture-recovery",
        "datasets": "fixture-datasets",
        "backups": "fixture-backups",
    }
    assert config["storageQuotaBytes"] == config["s3"]["quotaBytes"] == 123456
    assert config["s3"]["signingKeyFile"] == str(tmp_path / "signing.key")
    assert "never-publish" not in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["missing", "empty", "conflict", "oversized"])
def test_secret_file_errors_never_include_secret_values(tmp_path, monkeypatch, kind):
    source = tmp_path / "secret"
    if kind == "empty":
        source.write_text("")
    elif kind == "oversized":
        source.write_text("never-publish-secret" * 10000)
    elif kind == "conflict":
        source.write_text("never-publish-file-secret")
        monkeypatch.setenv("HETEROES_DATABASE_URL", "never-publish-env-secret")
    monkeypatch.setenv("HETEROES_DATABASE_URL_FILE", str(source))
    with pytest.raises(ValueError) as error:
        load_config()
    assert "never-publish" not in str(error.value)


@pytest.mark.parametrize("value", ["0", "-1", "not-an-integer", str(2**80)])
def test_storage_quota_configuration_requires_a_bounded_positive_integer(monkeypatch, value):
    monkeypatch.setenv("HETEROES_STORAGE_QUOTA_BYTES", value)
    with pytest.raises(ValueError, match="HETEROES_STORAGE_QUOTA_BYTES"):
        load_config()


def test_present_but_malformed_private_configuration_is_not_ignored(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text('["never-publish-config-marker"]')
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(tmp_path))
    monkeypatch.setenv("HETEROES_AUTH_MODE", "oidc")
    with pytest.raises(ValueError) as error:
        load_config()
    assert "never-publish" not in str(error.value)


@pytest.mark.parametrize("override", [False, True])
def test_optional_malformed_private_configuration_falls_back_to_an_object(tmp_path, monkeypatch, override):
    (tmp_path / "config.json").write_text('["never-publish-config-marker"]')
    if override:
        monkeypatch.setenv("HETEROES_PUBLIC_URL", "https://cloud.example.test")
    config = load_config(tmp_path, optional=True)
    assert isinstance(config, dict)
    assert config.get("publicWebUrl") == ("https://cloud.example.test" if override else None)


def test_environment_only_installer_manifest_keeps_private_bulk_urls(tmp_path, monkeypatch):
    from backend.apps.factory import create_app
    from backend.services.devices import AgentRuntime

    web, downloads = tmp_path / "web", tmp_path / "downloads"
    (web / "assets").mkdir(parents=True)
    downloads.mkdir()
    (web / "index.html").write_text("<title>Environment fixture</title>")
    (downloads / "manifest.json").write_text('{"installers":[{"name":"fixture.exe","url":"/downloads/fixture.exe"}]}')
    monkeypatch.setenv("HETEROES_PUBLIC_URL", "https://cloud.example.test")
    monkeypatch.setenv("HETEROES_BULK_API_URL", "http://100.64.0.10:18000")
    app = create_app(
        tmp_path / "manifest.sqlite",
        {},
        AgentRuntime(),
        dispatch=False,
        web_directory=web,
        downloads_directory=downloads,
    )
    with TestClient(app) as client:
        result = client.get("/downloads/manifest.json").json()
        assert result["privateTransferRequired"] is True
        assert result["installers"][0]["url"] == "http://100.64.0.10:18000/downloads/fixture.exe"


@pytest.mark.sqlite_file
def test_environment_only_oidc_application_needs_no_credentials_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HETEROES_STATE_DIRECTORY", str(tmp_path / "state"))
    monkeypatch.setenv("HETEROES_DATABASE_URL", "sqlite:///" + str(tmp_path / "state/product.sqlite"))
    monkeypatch.setenv("HETEROES_AUTH_MODE", "oidc")
    monkeypatch.setenv("HETEROES_OIDC_ISSUER", "https://identity.example.test/realms/lab")
    monkeypatch.setenv("HETEROES_OIDC_JWKS_URL", "http://127.0.0.1:1/jwks")
    monkeypatch.setenv("HETEROES_PUBLIC_URL", "https://cloud.example.test")
    monkeypatch.setenv("HETEROES_BULK_API_URL", "http://100.64.0.10:18000")
    app = app_from_environment()
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200
        assert client.get("/api/v1/health").json()["uiUrl"] == "https://cloud.example.test"
        assert app.state.store.runtime.public_web_url() == "https://cloud.example.test"
        assert client.post("/api/v1/auth/login", json={}).status_code == 404
    assert not (tmp_path / "state/credentials.json").exists()
    assert "never-publish" not in capsys.readouterr().out


@pytest.mark.sqlite_file
def test_local_environment_only_authentication_requires_explicit_bootstrap_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("HETEROES_STATE_DIRECTORY", str(tmp_path / "state"))
    with pytest.raises(ValueError, match="credentials"):
        app_from_environment()
    source = tmp_path / "bootstrap.json"
    source.write_text('{"users":{"admin":"never-publish-bootstrap-password"}}')
    monkeypatch.setenv("HETEROES_CREDENTIALS_FILE", str(source))
    app = app_from_environment()
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "never-publish-bootstrap-password"}
            ).status_code
            == 200
        )


if all(
    os.environ.get(name)
    for name in ("HETEROES_TEST_MINIO_ENDPOINT", "HETEROES_TEST_MINIO_ACCESS_KEY", "HETEROES_TEST_MINIO_SECRET_KEY")
):
    from test_s3_backend import s3 as s3

    def test_environment_only_factory_reaches_actual_minio_with_the_selected_buckets(s3, lab, tmp_path, monkeypatch):
        import hashlib

        original, config = s3
        _, store, _, _ = lab
        target = store.database.url
        if store.database.dialect == "postgresql":
            with store.db() as db:
                schema = db.execute("SELECT current_schema()").fetchone()[0]
            target = target.set(query={"options": "-csearch_path=" + schema})
        for name, value in {
            "HETEROES_STATE_DIRECTORY": str(tmp_path / "environment-state"),
            "HETEROES_DATABASE_URL": target.render_as_string(hide_password=False),
            "HETEROES_SERVICE": "api" if store.database.dialect == "postgresql" else "all",
            "HETEROES_AUTH_MODE": "oidc",
            "HETEROES_OIDC_ISSUER": "https://identity.example.test/realms/lab",
            "HETEROES_OIDC_JWKS_URL": "http://127.0.0.1:1/jwks",
            "HETEROES_STORAGE_MODE": "s3",
            "HETEROES_STORAGE_INTERNAL_ENDPOINT": config["endpointUrl"],
            "HETEROES_STORAGE_DEVICE_ENDPOINT": config["deviceEndpointUrl"],
            "HETEROES_STORAGE_ACCESS_KEY_ID": config["accessKeyId"],
            "HETEROES_STORAGE_SECRET_ACCESS_KEY": config["secretAccessKey"],
            **{
                "HETEROES_STORAGE_" + purpose.upper() + "_BUCKET": bucket
                for purpose, bucket in config["buckets"].items()
            },
        }.items():
            monkeypatch.setenv(name, value)
        app = app_from_environment()
        with TestClient(app) as client:
            assert client.get("/readyz").status_code == 200
            backend = app.state.storage.backend
            assert backend.mode == "s3" and backend._buckets == config["buckets"]
            payload = b"environment-only dataset bytes"
            key = "objects/" + hashlib.sha256(payload).hexdigest()
            backend.for_purpose("datasets").put(key, payload)
            assert b"".join(original.for_purpose("datasets").get(key)) == payload
