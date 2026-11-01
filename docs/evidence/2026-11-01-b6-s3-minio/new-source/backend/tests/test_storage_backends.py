"""One manifest/quota contract on actual local disk and actual MinIO, with worker-style signed URL I/O."""

import json
import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.services.devices import AgentRuntime
from backend.services.recovery_storage import RecoveryStorage, QuotaExceeded
from backend.services.store import Store
from backend.storage.local_backend import LocalBackend
from test_recovery_storage import manifest

if os.environ.get("HETEROES_TEST_MINIO_ENDPOINT"):
    from test_s3_backend import s3 as s3, put_url, read_url


@pytest.fixture(params=["local"] + (["s3"] if os.environ.get("HETEROES_TEST_MINIO_ENDPOINT") else []))
def real_storage(request, tmp_path):
    if request.param == "local":
        backend = LocalBackend(tmp_path / "bulk", tmp_path / "private/storage.key", "http://127.0.0.1:18052")
    else:
        backend, _ = request.getfixturevalue("s3")
    store = Store(tmp_path / "state/product.sqlite", {}, AgentRuntime(backend))
    storage = RecoveryStorage(store, backend, quota_bytes=10_000_000)
    app = FastAPI()
    backend.install_routes(app)
    with TestClient(app) as client:

        def put(plan, payload):
            if backend.mode == "local":
                response = client.put(urlsplit(plan["url"]).path, headers=plan["headers"], content=payload)
                assert response.status_code == 200
            else:
                assert put_url(plan["url"], payload, plan["headers"])[0] == 200

        def read(url):
            return client.get(urlsplit(url).path).content if backend.mode == "local" else read_url(url)

        yield backend, storage, store, put, read
    store.close()


def test_manifest_commit_deduplication_download_and_byte_quota_are_portable(real_storage):
    backend, storage, store, put, read = real_storage
    m = manifest()
    plan = storage.begin(m)
    assert len(plan["objects"]) == 1
    with pytest.raises(FileNotFoundError):
        b"".join(backend.get("manifests/" + m["pointId"] + ".json"))
    for entry in plan["objects"]:
        put(entry, b"weights")
        storage.complete_object(m["pointId"], entry["sha256"], [])
    storage.verify(m["pointId"])
    assert storage.points(m["runId"])[0]["status"] == "READY"
    assert json.loads(b"".join(backend.get("manifests/" + m["pointId"] + ".json"))) == m
    assert read(backend.download_url("objects/" + m["childWeightsSha256"])) == b"weights"
    assert storage.begin(m) == {"pointId": m["pointId"], "status": "READY", "objects": []}
    assert storage.usage()["storageMode"] == backend.mode
    storage.quota = 1
    with pytest.raises(QuotaExceeded):
        storage.begin(manifest(b"a second payload", point="c" * 32))


def test_wrong_uploaded_content_never_publishes_a_manifest_on_either_backend(real_storage):
    backend, storage, store, put, read = real_storage
    m = manifest()
    plan = storage.begin(m)
    put(plan["objects"][0], b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        storage.verify(m["pointId"])
    assert storage.points(m["runId"])[0]["status"] == "ERROR"
    with pytest.raises(FileNotFoundError):
        b"".join(backend.get("manifests/" + m["pointId"] + ".json"))


if all(
    os.environ.get(name) for name in ("HETEROES_TEST_MINIO_ENDPOINT", "HETEROES_TEST_DATABASE_URL", "HETEROES_PG_DUMP")
):

    def test_production_s3_postgres_backup_download_and_fresh_restore(s3, tmp_path, fresh_postgres_database):
        import hashlib
        from backend.db.engine import Database
        from backend.db.postgres_backup import restore_postgres
        from backend.services.metadata_backup import create_metadata_backup

        backend, config = s3
        source = Store(
            tmp_path / "source/product.sqlite",
            {"admin": "test-admin-pass"},
            AgentRuntime(backend),
            database_url=fresh_postgres_database(),
        )
        try:
            with source.db() as db:
                db.execute(
                    "INSERT INTO device_reservations(device_id,assignment_id) VALUES (:p0,:p1)",
                    ("offline-device", "unknown-owner"),
                )
                db.execute(
                    "INSERT INTO sessions(digest,user_id,expires) VALUES (:p0,:p1,:p2)",
                    ("fixture-session", "admin", 9999999999),
                )
            result = create_metadata_backup(source, RecoveryStorage(source, backend, quota_bytes=10_000_000))
            assert result["status"] == "READY"
            metadata = json.loads(b"".join(backend.get("metadata/" + result["pointId"] + "/manifest.json")))
            assert metadata["databaseDriver"] == "postgresql"
            assert (
                backend.client.head_object(Bucket=config["buckets"]["backups"], Key=metadata["objectKey"])[
                    "ContentLength"
                ]
                == metadata["sizeBytes"]
            )
            downloaded = tmp_path / "downloaded.pgdump"
            downloaded.write_bytes(b"".join(backend.get(metadata["objectKey"])))
            downloaded.chmod(0o600)
            with Database(fresh_postgres_database()) as target:
                receipt = restore_postgres(downloaded, metadata, target)
                with target.transaction() as db:
                    assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
                    assert (
                        db.execute("SELECT value FROM settings WHERE key=:p0", ("dispatchHold",)).fetchone()[0]
                        == "true"
                    )
                    assert db.execute("SELECT count(*) FROM device_reservations").fetchone()[0] == 1
            assert hashlib.sha256(downloaded.read_bytes()).hexdigest() == metadata["sha256"]
            if destination := os.environ.get("HETEROES_TEST_S3_RECEIPT_FILE"):
                from pathlib import Path

                Path(destination).write_text(
                    json.dumps(
                        {
                            "scope": "production S3Backend PostgreSQL dump -> actual MinIO backup bucket -> fresh PG restore",
                            "databaseDriver": "postgresql",
                            "bucket": config["buckets"]["backups"],
                            "sha256": metadata["sha256"],
                            "sizeBytes": metadata["sizeBytes"],
                            **receipt,
                        },
                        indent=2,
                    )
                    + "\n"
                )
        finally:
            source.close()
