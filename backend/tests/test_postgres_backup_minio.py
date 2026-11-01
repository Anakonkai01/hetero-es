"""Explicit real MinIO integration: production backup logic uploads, verifies, downloads and restores PostgreSQL."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from backend.db.engine import Database
from backend.db.postgres_backup import restore_postgres
from backend.services.devices import AgentRuntime
from backend.services.metadata_backup import create_metadata_backup
from backend.services.recovery_storage import RecoveryStorage
from backend.services.store import Store


if all(
    os.environ.get(key) for key in ("HETEROES_TEST_DATABASE_URL", "HETEROES_PG_DUMP", "HETEROES_TEST_MINIO_ENDPOINT")
):

    class SDKBackupBucket:
        """Test-only SDK adapter; every operation goes to the real owned MinIO endpoint, without presigned URLs."""

        def __init__(self, client, bucket):
            self.client, self.bucket, self.keys = client, bucket, set()

        def put(self, key, data):
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
            self.keys.add(key)

        def put_file(self, key, source):
            self.client.upload_file(str(source), self.bucket, key)
            self.keys.add(key)

        def get(self, key):
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
            try:
                yield from body.iter_chunks(chunk_size=65536)
            finally:
                body.close()

        def delete(self, key):
            self.client.delete_object(Bucket=self.bucket, Key=key)
            self.keys.discard(key)

        def inventory(self):
            return sum(
                row["Size"]
                for page in self.client.get_paginator("list_objects_v2").paginate(
                    Bucket=self.bucket, Prefix="metadata/"
                )
                for row in page.get("Contents", [])
            )

    @pytest.fixture
    def bucket():
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError

        client = boto3.client(
            "s3",
            endpoint_url=os.environ["HETEROES_TEST_MINIO_ENDPOINT"],
            region_name="us-east-1",
            aws_access_key_id=os.environ["HETEROES_TEST_MINIO_ACCESS_KEY"],
            aws_secret_access_key=os.environ["HETEROES_TEST_MINIO_SECRET_KEY"],
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=3,
                read_timeout=10,
                retries={"max_attempts": 2},
                proxies={},
            ),
        )
        name = "heteroes-backups"
        try:
            client.head_bucket(Bucket=name)
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"404", "NoSuchBucket"}:
                raise
            client.create_bucket(Bucket=name)
        backend = SDKBackupBucket(client, name)
        try:
            yield backend
        finally:
            for key in list(backend.keys):
                backend.delete(key)
            client.close()

    def test_real_minio_upload_download_and_fresh_database_restore(tmp_path, fresh_postgres_database, bucket):
        source = Store(
            tmp_path / "source/product.sqlite",
            {"admin": "backup-fixture-password"},
            AgentRuntime(),
            database_url=fresh_postgres_database(),
        )
        try:
            with source.db() as db:
                db.execute(
                    "INSERT INTO device_reservations(device_id,assignment_id) VALUES (:p0,:p1)",
                    ("offline-device", "unknown-assignment"),
                )
                db.execute(
                    "INSERT INTO sessions(digest,user_id,expires) VALUES (:p0,:p1,:p2)",
                    ("fixture-session", "admin", 9999999999),
                )
            storage = RecoveryStorage(source, bucket, quota_bytes=20_000_000)
            result = create_metadata_backup(source, storage)
            assert result["status"] == "READY"
            prefix = "metadata/" + result["pointId"]
            manifest = json.loads(b"".join(bucket.get(prefix + "/manifest.json")))
            downloaded = tmp_path / "downloaded.pgdump"
            with downloaded.open("xb") as stream:
                downloaded.chmod(0o600)
                for chunk in bucket.get(manifest["objectKey"]):
                    stream.write(chunk)
            digest = hashlib.sha256(downloaded.read_bytes()).hexdigest()
            assert digest == manifest["sha256"] and downloaded.stat().st_size == manifest["sizeBytes"]
            with Database(fresh_postgres_database()) as target:
                receipt = restore_postgres(downloaded, manifest, target)
                with target.transaction() as db:
                    assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
                    assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
                    assert [
                        tuple(row) for row in db.execute("SELECT device_id,assignment_id FROM device_reservations")
                    ] == [("offline-device", "unknown-assignment")]
                    assert (
                        db.execute("SELECT value FROM settings WHERE key=:p0", ("dispatchHold",)).fetchone()[0]
                        == "true"
                    )
            proof = {
                "scope": "actual PostgreSQL17 dump -> actual MinIO bucket -> download -> fresh PostgreSQL restore",
                "sha256": digest,
                "sizeBytes": manifest["sizeBytes"],
                "bucket": bucket.bucket,
                "status": result["status"],
                **receipt,
            }
            destination = os.environ.get("HETEROES_TEST_MINIO_RECEIPT_FILE")
            if destination:
                Path(destination).write_text(json.dumps(proof, indent=2) + "\n")
        finally:
            source.close()

    def test_real_minio_readback_corruption_never_publishes_a_ready_manifest(tmp_path, fresh_postgres_database, bucket):
        source = Store(tmp_path / "corrupt/product.sqlite", {}, AgentRuntime(), database_url=fresh_postgres_database())
        original = bucket.put_file

        def corrupt(key, path):
            original(key, path)
            bucket.put(key, b"corrupt-network-fixture")

        bucket.put_file = corrupt
        try:
            result = create_metadata_backup(source, RecoveryStorage(source, bucket, quota_bytes=20_000_000))
            assert result["status"] == "PENDING" and result["errorType"] == "ValueError"
            prefix = "metadata/" + result["pointId"]
            published = [
                row["Key"]
                for row in bucket.client.list_objects_v2(Bucket=bucket.bucket, Prefix=prefix).get("Contents", [])
            ]
            assert prefix + "/manifest.json" not in published
            assert (Path(source.path).parent / "metadata-backups" / result["pointId"] / "product.pgdump").is_file()
        finally:
            source.close()
