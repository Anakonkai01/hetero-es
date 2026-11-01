"""Only bounded dataset bytes cross the public proxy; bulk S3 URLs retain the private device origin."""

import hashlib
import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_s3_backend import configuration


if os.environ.get("HETEROES_TEST_MINIO_ENDPOINT"):
    from test_s3_backend import s3 as s3

    @pytest.fixture
    def public(s3):
        backend, config = s3
        app = FastAPI()
        backend.install_routes(app)
        with TestClient(app) as client:
            yield backend, backend.for_purpose("datasets"), config, client

    def test_real_public_dataset_upload_then_download_goes_to_the_dataset_bucket(public):
        backend, datasets, config, client = public
        payload = b"actual dataset bytes"
        key = "uploads/" + "a" * 64 + "/" + "b" * 32
        plan = datasets.upload_plan(key, len(payload), public_base="https://cloud.example.test")
        assert urlsplit(plan["url"]).netloc == urlsplit(config["deviceEndpointUrl"]).netloc
        response = client.put(urlsplit(plan["publicUrl"]).path, content=payload)
        assert response.status_code == 200 and response.json()["sizeBytes"] == len(payload)
        assert b"".join(datasets.get(key)) == payload
        with pytest.raises(FileNotFoundError):
            b"".join(backend.get(key))
        etag, chunks = datasets.read_version(key)
        assert b"".join(chunks) == payload
        sha = hashlib.sha256(payload).hexdigest()
        datasets.publish_upload(key, "objects/" + sha, etag)
        public_url = datasets.public_study_url("https://cloud.example.test", "objects/" + sha)
        assert client.get(urlsplit(public_url).path).content == payload
        assert backend.public_study_url("https://cloud.example.test", "objects/" + sha) is None

    def test_public_capabilities_reject_tamper_method_and_bucket_confusion(public):
        backend, datasets, _, client = public
        key = "uploads/" + "a" * 64 + "/" + "b" * 32
        plan = datasets.upload_plan(key, 4, public_base="https://cloud.example.test")
        path = urlsplit(plan["publicUrl"]).path
        assert client.put(path + "0", content=b"data").status_code == 403
        wrong = "/api/v1/public-study/" + datasets._signer._token("PUT-PUBLIC", key, 4, 900)
        assert client.get(wrong).status_code == 403
        other = "/api/v1/public-upload/" + backend._signer._token("PUT-PUBLIC", key, 4, 900)
        assert client.put(other, content=b"data").status_code == 403
        # These reserved bulk API paths never relay large S3 objects through the public controller.
        assert client.get("/api/v1/local-storage/unused").status_code == 403
        assert client.put("/api/v1/local-storage/unused", content=b"data").status_code == 403

    def test_signed_length_and_public_size_limit_are_checked_again_at_the_proxy(public, monkeypatch):
        import backend.storage.s3_backend as module

        _, datasets, _, client = public
        key = "uploads/" + "a" * 64 + "/" + "b" * 32
        plan = datasets.upload_plan(key, 4, public_base="https://cloud.example.test")
        assert client.put(urlsplit(plan["publicUrl"]).path, content=b"bad").status_code == 400
        assert (
            client.put(urlsplit(plan["publicUrl"]).path, content=b"data", headers={"Content-Length": "3"}).status_code
            == 400
        )
        assert (
            client.put(urlsplit(plan["publicUrl"]).path, content=b"extra", headers={"Content-Length": "4"}).status_code
            == 413
        )
        monkeypatch.setattr(module, "PUBLIC_STUDY_MAX_BYTES", 3)
        assert "publicUrl" not in datasets.upload_plan(key, 4, public_base="https://cloud.example.test")
        forged = "/api/v1/public-upload/" + datasets._signer._token("PUT-PUBLIC", key, 4, 900)
        assert client.put(forged, content=b"data").status_code == 403
        sha = hashlib.sha256(b"data").hexdigest()
        datasets.put("objects/" + sha, b"data")
        assert datasets.public_study_url("https://cloud.example.test", "objects/" + sha) is None
        forged = "/api/v1/public-study/" + datasets._signer._token("GET-PUBLIC", "objects/" + sha, None, 300)
        assert client.get(forged).status_code == 404

    def test_public_signing_key_is_stable_across_replicas_and_upload_scratch_is_removed(public):
        from backend.storage.s3_backend import S3Backend

        backend, datasets, config, client = public
        key = "uploads/" + "c" * 64 + "/" + "d" * 32
        plan = datasets.upload_plan(key, 4, public_base="https://cloud.example.test")
        restarted = S3Backend(config)
        try:
            app = FastAPI()
            restarted.install_routes(app)
            with TestClient(app) as replica:
                assert replica.put(urlsplit(plan["publicUrl"]).path, content=b"data").status_code == 200
            assert b"".join(datasets.get(key)) == b"data"
            assert not list(backend.root.glob(".public-upload-*"))
        finally:
            restarted.close()


def test_s3_factory_selects_cloud_backend_and_closes_it_after_background_threads(tmp_path, monkeypatch):
    from backend.apps.factory import _app_from_config
    from backend.storage.s3_backend import S3Backend

    closed = []
    original = S3Backend.close

    def close(self):
        closed.append(self)
        return original(self)

    monkeypatch.setattr(S3Backend, "close", close)
    app = _app_from_config(
        tmp_path,
        {"users": {}},
        {
            "deploymentMode": "agent",
            "productStateDirectory": str(tmp_path / "state"),
            "apiUrl": "https://cloud.example.test",
            "storageMode": "s3",
            "s3": configuration(tmp_path),
        },
        None,
    )
    with TestClient(app) as client:
        assert app.state.storage.backend.mode == "s3"
        assert client.get("/api/v1/health").json()["recoveryStorageMode"] == "s3"
    assert closed == [app.state.storage.backend]


def test_s3_roles_preserve_the_exact_product_route_partition(tmp_path):
    from contextlib import ExitStack
    from backend.apps.factory import create_app
    from backend.apps.routing import inventory
    from backend.services.devices import AgentRuntime
    from backend.storage.s3_backend import S3Backend
    from test_service_routes import BASELINE

    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html>fixture")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    with ExitStack() as cleanup:
        contracts = {}
        for role in ["all", "api", "devices", "storage", "scheduler"]:
            backend = S3Backend(configuration(tmp_path / role))
            cleanup.callback(backend.close)
            app = create_app(
                tmp_path / role / "product.sqlite",
                {},
                AgentRuntime(backend),
                dispatch=False,
                service=role,
                web_directory=web,
                downloads_directory=downloads,
            )
            cleanup.callback(app.state.store.close)
            contracts[role] = {(row["method"], row["path"]) for row in inventory(app)["product"]}
        expected = {(method, row["path"]) for row in BASELINE for method in row.get("methods", [])}
        assert contracts["all"] == expected and len(contracts["all"]) == 111
        owned = [pair for role in ["api", "devices", "storage"] for pair in contracts[role]]
        assert len(owned) == len(set(owned)) and set(owned) == contracts["all"]
        assert not contracts["scheduler"]
