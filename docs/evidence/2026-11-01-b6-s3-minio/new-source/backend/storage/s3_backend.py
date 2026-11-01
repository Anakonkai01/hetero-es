"""Private S3/MinIO storage: internal I/O, separate device presigning and explicit data/backup buckets."""

import hashlib
import hmac
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from ..core.addresses import endpoint
from .local_backend import KEY, LocalBackend, PUBLIC_STUDY_MAX_BYTES
from ..core.errors import ServiceError

PART_BYTES = 64 * 1024**2
_BUCKET = re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]\Z")


def _internal_endpoint(value):
    try:
        parsed = urlsplit(value)
        docker_host = parsed.hostname == "localhost" or bool(
            re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]{0,62}", parsed.hostname or "")
        )
        if (
            docker_host
            and parsed.scheme in {"http", "https"}
            and not (
                parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")
            )
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        ):
            return value.rstrip("/")
        # Public internal endpoints still need HTTPS; HTTP numerical endpoints must be private.
        return endpoint(value)
    except (TypeError, ValueError):
        raise ValueError("Use an explicit internal S3 endpoint origin") from None


class S3Backend:
    mode = "s3"

    def __init__(self, config):
        internal = _internal_endpoint(config["endpointUrl"])
        private = endpoint(config["deviceEndpointUrl"], private=True)
        if any(
            not isinstance(config.get(name), str) or not config[name] for name in ("accessKeyId", "secretAccessKey")
        ):
            raise ValueError("Explicit object-storage credentials are required")
        buckets = config.get("buckets")
        if (
            not isinstance(buckets, dict)
            or set(buckets) != {"recovery", "datasets", "backups"}
            or any(not isinstance(name, str) or not _BUCKET.fullmatch(name) for name in buckets.values())
            or len(set(buckets.values())) != 3
        ):
            raise ValueError("Configure distinct recovery, datasets and backups bucket names")
        self.root = Path(config["stagingDirectory"]).resolve()
        if self.root == Path("/mnt/sekai") or Path("/mnt/sekai") in self.root.parents:
            raise ValueError("Sekai is not authorized for HeteroES storage")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._key_file = Path(config["signingKeyFile"])
        self._private_endpoint = private
        self._buckets, self._purpose, self._owner, self._views = dict(buckets), "recovery", self, {}
        self.quota_bytes = config.get("quotaBytes", 200_000_000_000)
        self._signer = self._signer_for("recovery")
        import boto3
        from botocore.config import Config

        options = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            proxies={},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 2},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
        credentials = dict(
            region_name=config.get("region", "us-east-1"),
            aws_access_key_id=config["accessKeyId"],
            aws_secret_access_key=config["secretAccessKey"],
            config=options,
        )
        self.client = boto3.client("s3", endpoint_url=internal, **credentials)
        self.presigner = boto3.client("s3", endpoint_url=private, **credentials)

    def _signer_for(self, purpose):
        signer = LocalBackend(self.root / ("public-" + purpose), self._key_file, self._private_endpoint)
        # Public proxy capabilities are scoped to the actual bucket, including when several roles share a key file.
        signer.secret = hmac.new(signer.secret, self._buckets[purpose].encode(), hashlib.sha256).digest()
        return signer

    def for_purpose(self, purpose):
        if purpose not in self._buckets:
            raise ValueError("Unknown storage purpose")
        owner = self._owner
        if purpose == "recovery":
            return owner
        if purpose not in owner._views:
            view = object.__new__(S3Backend)
            view.__dict__ = owner.__dict__.copy()
            view._purpose = purpose
            view._signer = owner._signer_for(purpose)
            owner._views[purpose] = view
        return owner._views[purpose]

    def _bucket(self, key):
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise ValueError("Unsafe storage key")
        if key.startswith("metadata/"):
            if self._purpose == "datasets":
                raise ValueError("Metadata is outside dataset storage")
            return self._buckets["backups"]
        if self._purpose == "backups":
            raise ValueError("Only metadata belongs in backup storage")
        return self._buckets[self._purpose]

    def _call(self, operation, **parameters):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return getattr(self.client, operation)(**parameters)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if operation == "abort_multipart_upload" and code == "NoSuchUpload":
                return None
            if code in {"NoSuchKey", "NotFound", "404"}:
                raise FileNotFoundError("Storage object unavailable") from None
            raise ValueError("Object storage operation failed") from None
        except BotoCoreError:
            raise ValueError("Object storage operation failed") from None

    def inventory(self):
        # Quota is shared by all three purposes, and incomplete multipart bytes count too. No R2 request metering.
        total = 0
        for bucket in self._buckets.values():
            for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
                total += sum(item["Size"] for item in page.get("Contents", []))
            for page in self.client.get_paginator("list_multipart_uploads").paginate(Bucket=bucket):
                for upload in page.get("Uploads", []):
                    for parts in self.client.get_paginator("list_parts").paginate(
                        Bucket=bucket, Key=upload["Key"], UploadId=upload["UploadId"]
                    ):
                        total += sum(item["Size"] for item in parts.get("Parts", []))
        return total

    @staticmethod
    def _chunks(response):
        try:
            yield from response["Body"].iter_chunks(chunk_size=1024**2)
        finally:
            response["Body"].close()

    def get(self, key):
        response = self._call("get_object", Bucket=self._bucket(key), Key=key)
        yield from self._chunks(response)

    def read_version(self, key):
        response = self._call("get_object", Bucket=self._bucket(key), Key=key)
        return response["ETag"], self._chunks(response)

    def publish_upload(self, source, destination, etag):
        if not source.startswith("uploads/") or not destination.startswith("objects/"):
            raise ValueError("Invalid verified publication keys")
        bucket, target = self._bucket(source), self._bucket(destination)
        self._call(
            "copy_object",
            Bucket=target,
            Key=destination,
            CopySource={"Bucket": bucket, "Key": source},
            CopySourceIfMatch=etag,
        )
        self.delete(source)

    def put(self, key, data):
        self._call("put_object", Bucket=self._bucket(key), Key=key, Body=data)

    def put_file(self, key, source, expected=None):
        bucket = self._bucket(key)
        if expected is not None:
            with Path(source).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError("Publication hash mismatch")
        # An SDK file body streams from disk; it does not retain the whole payload in memory.
        with Path(source).open("rb") as stream:
            self._call("put_object", Bucket=bucket, Key=key, Body=stream)

    def delete(self, key):
        self._call("delete_object", Bucket=self._bucket(key), Key=key)

    def upload_plan(self, key, size, public_base=None):
        bucket = self._bucket(key)
        if not key.startswith("uploads/") or type(size) is not int or not 0 < size <= 5_000_000_000:
            raise ValueError("Invalid upload size or key")
        if size <= PART_BYTES:
            plan = {
                "mode": "single",
                "key": key,
                "url": self.presigner.generate_presigned_url(
                    "put_object", Params={"Bucket": bucket, "Key": key, "ContentLength": size}, ExpiresIn=900
                ),
                "headers": {"Content-Length": str(size)},
            }
        else:
            upload_id = self._call("create_multipart_upload", Bucket=bucket, Key=key)["UploadId"]
            parts = []
            for number in range(1, math.ceil(size / PART_BYTES) + 1):
                length = min(PART_BYTES, size - (number - 1) * PART_BYTES)
                url = self.presigner.generate_presigned_url(
                    "upload_part",
                    Params={
                        "Bucket": bucket,
                        "Key": key,
                        "UploadId": upload_id,
                        "PartNumber": number,
                        "ContentLength": length,
                    },
                    ExpiresIn=900,
                )
                parts.append({"number": number, "offset": (number - 1) * PART_BYTES, "sizeBytes": length, "url": url})
            plan = {"mode": "multipart", "key": key, "uploadId": upload_id, "parts": parts}
        if self._purpose == "datasets" and public_base and size <= PUBLIC_STUDY_MAX_BYTES:
            plan["publicUrl"] = (
                public_base.rstrip("/") + "/api/v1/public-upload/" + self._signer._token("PUT-PUBLIC", key, size, 900)
            )
        return plan

    def complete(self, key, upload_id, parts):
        self._call(
            "complete_multipart_upload",
            Bucket=self._bucket(key),
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

    def abort(self, key, upload_id):
        self._call("abort_multipart_upload", Bucket=self._bucket(key), Key=key, UploadId=upload_id)

    def download_url(self, key):
        return self.presigner.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket(key), "Key": key}, ExpiresIn=60
        )

    def public_study_url(self, public_base, key):
        if self._purpose != "datasets" or not key.startswith("objects/"):
            return None
        try:
            size = self._call("head_object", Bucket=self._bucket(key), Key=key)["ContentLength"]
        except FileNotFoundError:
            return None
        if size > PUBLIC_STUDY_MAX_BYTES:
            return None
        return public_base.rstrip("/") + "/api/v1/public-study/" + self._signer._token("GET-PUBLIC", key, None, 300)

    def ready(self):
        for bucket in self._buckets.values():
            self._call("head_bucket", Bucket=bucket)

    def public_upload_grant(self, token, content_length):
        grant = self._signer.grant(token, "PUT-PUBLIC")
        if (
            self._purpose != "datasets"
            or not grant["key"].startswith("uploads/")
            or not 0 < grant["size"] <= PUBLIC_STUDY_MAX_BYTES
        ):
            raise ServiceError(403, "Dataset upload capability required")
        if content_length != str(grant["size"]):
            raise ServiceError(400, "Signed upload length required")
        return grant

    def public_download(self, token):
        grant = self._signer.grant(token, "GET-PUBLIC")
        if self._purpose != "datasets" or not grant["key"].startswith("objects/"):
            raise ServiceError(403, "Dataset download capability required")
        try:
            response = self._call("get_object", Bucket=self._bucket(grant["key"]), Key=grant["key"])
        except FileNotFoundError:
            raise ServiceError(404, "Object unavailable") from None
        if response["ContentLength"] > PUBLIC_STUDY_MAX_BYTES:
            response["Body"].close()
            raise ServiceError(404, "Object unavailable")
        return self._chunks(response), response["ContentLength"]

    def install_routes(self, app):
        from ..api.s3_storage import install_routes

        return install_routes(app, self.for_purpose("datasets"))

    def close(self):
        self._owner.client.close()
        self._owner.presigner.close()
