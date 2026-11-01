"""S3 contracts: explicit buckets/private presigning and actual worker-style MinIO HTTP, without R2 assumptions."""

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import uuid

import pytest

from backend.storage.s3_backend import S3Backend
from heteroes.http_safety import opener
from urllib.request import Request


def configuration(tmp_path, **changes):
    return {
        "endpointUrl": "http://minio:9000",
        "deviceEndpointUrl": "http://127.0.0.1:19000",
        "accessKeyId": "unit-access-id",
        "secretAccessKey": "unit-nondeployed-secret",
        "buckets": {"recovery": "heteroes-recovery", "datasets": "heteroes-datasets", "backups": "heteroes-backups"},
        "stagingDirectory": str(tmp_path / "staging"),
        "signingKeyFile": str(tmp_path / "private/storage.key"),
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"endpointUrl": "http://public.example.test"},
        {"accessKeyId": ""},
        {"secretAccessKey": ""},
        {"endpointUrl": "http://minio:9000/path"},
        {"deviceEndpointUrl": "https://public.example.test"},
        {"deviceEndpointUrl": "http://8.8.8.8:9000"},
        {"deviceEndpointUrl": "http://user:password@127.0.0.1:19000"},
        {"buckets": {"recovery": "same-bucket", "datasets": "same-bucket", "backups": "other-bucket"}},
        {"buckets": {"recovery": "only-one"}},
    ],
)
def test_configuration_rejects_public_bulk_or_ambiguous_buckets_before_network(tmp_path, changes):
    with pytest.raises(ValueError):
        S3Backend(configuration(tmp_path, **changes))


def test_internal_docker_http_and_private_presigner_need_no_r2_account_confirmation(tmp_path):
    backend = S3Backend(configuration(tmp_path))
    try:
        assert backend.mode == "s3" and backend.root.is_dir()
        assert backend.client.meta.endpoint_url == "http://minio:9000"
        assert backend.presigner.meta.endpoint_url == "http://127.0.0.1:19000"
        assert backend.client.meta.config.signature_version == "s3v4"
        assert backend.client.meta.config.s3["addressing_style"] == "path"
        assert backend.client.meta.config.proxies == {}
        with pytest.raises(ValueError):
            backend.for_purpose("unrelated")
        for key in ["../outside", "objects/not-a-hash", "metadata/../../credentials.json"]:
            with pytest.raises(ValueError):
                backend.download_url(key)
    finally:
        backend.close()


if all(
    os.environ.get(name)
    for name in ("HETEROES_TEST_MINIO_ENDPOINT", "HETEROES_TEST_MINIO_ACCESS_KEY", "HETEROES_TEST_MINIO_SECRET_KEY")
):

    @pytest.fixture
    def s3(tmp_path):
        endpoint = os.environ["HETEROES_TEST_MINIO_ENDPOINT"]
        suffix = uuid.uuid4().hex
        buckets = {
            purpose: "heteroes-test-" + purpose + "-" + suffix for purpose in ("recovery", "datasets", "backups")
        }
        # Same real server through distinct internal/device origins; the device URL is what the HTTP test actually uses.
        config = configuration(
            tmp_path,
            endpointUrl=endpoint.replace("127.0.0.1", "localhost"),
            deviceEndpointUrl=endpoint,
            accessKeyId=os.environ["HETEROES_TEST_MINIO_ACCESS_KEY"],
            secretAccessKey=os.environ["HETEROES_TEST_MINIO_SECRET_KEY"],
            buckets=buckets,
        )
        backend = S3Backend(config)
        try:
            for bucket in buckets.values():
                backend.client.create_bucket(Bucket=bucket)
            yield backend, config
        finally:
            for bucket in buckets.values():
                for page in backend.client.get_paginator("list_multipart_uploads").paginate(Bucket=bucket):
                    for upload in page.get("Uploads", []):
                        backend.client.abort_multipart_upload(
                            Bucket=bucket, Key=upload["Key"], UploadId=upload["UploadId"]
                        )
                for page in backend.client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
                    for obj in page.get("Contents", []):
                        backend.client.delete_object(Bucket=bucket, Key=obj["Key"])
                backend.client.delete_bucket(Bucket=bucket)
            backend.close()

    def put_url(url, data, headers=None):
        with opener(proxy=False).open(
            Request(url, data=data, headers=headers or {}, method="PUT"), timeout=10
        ) as response:
            return response.status, response.headers.get("ETag")

    def read_url(url):
        with opener(proxy=False).open(url, timeout=10) as response:
            return response.read()

    def upload_key(payload):
        return "uploads/" + hashlib.sha256(payload).hexdigest() + "/" + uuid.uuid4().hex

    def test_real_single_upload_read_copy_and_device_download(s3):
        backend, config = s3
        payload = b"actual worker bytes"
        key = upload_key(payload)
        plan = backend.upload_plan(key, len(payload))
        assert plan["mode"] == "single" and urlsplit(plan["url"]).netloc == urlsplit(config["deviceEndpointUrl"]).netloc
        assert urlsplit(plan["url"]).path.startswith("/" + config["buckets"]["recovery"] + "/")
        assert put_url(plan["url"], payload, plan["headers"])[0] == 200
        etag, chunks = backend.read_version(key)
        assert b"".join(chunks) == payload
        sha = hashlib.sha256(payload).hexdigest()
        backend.publish_upload(key, "objects/" + sha, etag)
        assert read_url(backend.download_url("objects/" + sha)) == payload
        with pytest.raises(FileNotFoundError):
            b"".join(backend.get(key))
        assert backend.inventory() == len(payload)

    def test_real_dataset_and_backup_buckets_are_distinct_even_for_the_same_object_hash(s3, tmp_path):
        backend, config = s3
        dataset = backend.for_purpose("datasets")
        payload = b"dataset bytes"
        sha = hashlib.sha256(payload).hexdigest()
        key = "objects/" + sha
        dataset.put(key, payload)
        with pytest.raises(FileNotFoundError):
            b"".join(backend.get(key))
        assert read_url(dataset.download_url(key)) == payload
        assert urlsplit(dataset.download_url(key)).path.startswith("/" + config["buckets"]["datasets"] + "/")
        backup = "metadata/" + "a" * 32 + "/product.pgdump"
        source = tmp_path / "dump"
        source.write_bytes(b"pgdump bytes")
        backend.put_file(backup, source)
        assert b"".join(backend.get(backup)) == b"pgdump bytes"
        assert backend.client.head_object(Bucket=config["buckets"]["backups"], Key=backup)["ContentLength"] == 12
        assert backend.inventory() == len(payload) + 12
        assert backend.public_study_url("https://cloud.example.test", key) is None

    def test_real_multipart_parts_are_counted_completed_and_aborted(s3, monkeypatch):
        import backend.storage.s3_backend as module

        backend, _ = s3
        part = 5 * 1024**2
        monkeypatch.setattr(module, "PART_BYTES", part)
        payload = b"a" * part + b"final"
        key = upload_key(payload)
        plan = backend.upload_plan(key, len(payload))
        assert plan["mode"] == "multipart" and len(plan["parts"]) == 2
        completed = []
        for item in plan["parts"]:
            block = payload[item["offset"] : item["offset"] + item["sizeBytes"]]
            status, etag = put_url(item["url"], block, {"Content-Length": str(len(block))})
            assert status == 200
            completed.append({"PartNumber": item["number"], "ETag": etag})
        assert backend.inventory() == len(payload)
        backend.complete(key, plan["uploadId"], completed)
        assert b"".join(backend.get(key)) == payload
        abandoned = backend.upload_plan(upload_key(payload), len(payload))
        backend.abort(abandoned["key"], abandoned["uploadId"])
        backend.abort(abandoned["key"], abandoned["uploadId"])

    def test_changed_upload_etag_cannot_publish_verified_object(s3):
        backend, _ = s3
        payload = b"expected bytes"
        key = upload_key(payload)
        plan = backend.upload_plan(key, len(payload))
        put_url(plan["url"], payload, plan["headers"])
        etag, chunks = backend.read_version(key)
        assert b"".join(chunks) == payload
        put_url(plan["url"], b"x" * len(payload), plan["headers"])
        target = "objects/" + hashlib.sha256(payload).hexdigest()
        with pytest.raises(ValueError):
            backend.publish_upload(key, target, etag)
        with pytest.raises(FileNotFoundError):
            b"".join(backend.get(target))
        assert b"".join(backend.get(key)) != payload

    def test_file_publication_checks_expected_sha_before_sending_bytes(s3, tmp_path):
        backend, _ = s3
        source = tmp_path / "payload"
        source.write_bytes(b"stream file")
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        backend.put_file("objects/" + sha, source, sha)
        assert b"".join(backend.get("objects/" + sha)) == source.read_bytes()
        with pytest.raises(ValueError):
            backend.put_file("objects/" + "f" * 64, source, "f" * 64)
        with pytest.raises(FileNotFoundError):
            b"".join(backend.get("objects/" + "f" * 64))
