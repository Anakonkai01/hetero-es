"""Filesystem recovery storage with expiring scoped upload/download capabilities."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import time
import threading
from anyio import CancelScope

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

KEY = re.compile(
    r"(?:uploads/[a-f0-9]{64}/[a-f0-9]{32}|objects/[a-f0-9]{64}|"
    r"manifests/[a-f0-9]{32}\.json|metadata/[a-f0-9]{32}/(?:product\.sqlite|manifest\.json))"
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class _Upload:
    """One bounded streaming upload; each method runs off the API event loop."""

    def __init__(self):
        self.lock = threading.RLock()
        self.closed = False
        self.partial = None
        self.stream = None
        self.fd = None
        self.total = 0
        self.hasher = hashlib.sha256()

    def open(self, target, size):
        with self.lock:
            if self.closed:
                raise RuntimeError("Upload already closed")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.fd, partial = tempfile.mkstemp(prefix=".pending-", dir=target.parent)
            self.partial = Path(partial)
            self.target = target
            self.size = size
            self.stream = os.fdopen(self.fd, "wb")
            self.fd = None

    def write(self, chunk):
        with self.lock:
            self.total += len(chunk)
            if self.total > self.size:
                raise HTTPException(413, "Upload exceeds signed size")
            self.hasher.update(chunk)
            self.stream.write(chunk)

    def finish(self):
        with self.lock:
            self.stream.flush()
            os.fsync(self.stream.fileno())
            self.stream.close()
            if self.total != self.size:
                raise HTTPException(400, "Incomplete upload")
            try:
                os.link(self.partial, self.target)
            except FileExistsError:
                if digest(self.target) != self.hasher.hexdigest():
                    raise HTTPException(409, "Upload is immutable")
            return {"sizeBytes": self.total}

    def close(self):
        # Raw asyncio cancellation can leave a thread operation running. Wait
        # for its ownership before closing, even outside an AnyIO cancel scope.
        with self.lock:
            self.closed = True
            try:
                if self.stream is not None:
                    self.stream.close()
                elif self.fd is not None:
                    os.close(self.fd)
                    self.fd = None
            finally:
                if self.partial is not None:
                    self.partial.unlink(missing_ok=True)


PUBLIC_STUDY_MAX_BYTES = 64 * 1024**2  # datasets are at most 10 MB documents plus split files; never weights


class LocalBackend:
    mode = "local"

    def __init__(self, root, key_file, base_url, expected_uuid=None, metadata_root=None):
        from .devices import Enrollment

        # Same private LAN/Tailscale validation as the compute endpoint.
        self.base_url = Enrollment.private_compute(base_url)
        self.root = Path(root).resolve()
        self.expected_uuid = expected_uuid
        if expected_uuid is not None:
            if not re.fullmatch("[a-fA-F0-9-]+", expected_uuid):
                raise ValueError("Invalid storage volume UUID")
            self.check_volume()
        if self.root == Path("/mnt/sekai") or Path("/mnt/sekai") in self.root.parents:
            raise ValueError("Sekai is not authorized for HeteroES storage")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.metadata_root = Path(metadata_root).resolve() if metadata_root is not None else None
        if self.metadata_root is not None:
            self.metadata_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt" and self.metadata_root.stat().st_mode & 0o077:
                raise ValueError("Metadata storage directory must be private")
        key_file = Path(key_file)
        if key_file.is_symlink():
            raise ValueError("Storage signing key cannot be a symlink")
        key_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not key_file.exists():
            with key_file.open("xb") as stream:
                os.chmod(key_file, 0o600)
                stream.write(secrets.token_bytes(32))
        if os.name != "nt" and key_file.stat().st_mode & 0o077:
            raise ValueError("Storage signing key must be private")
        self.secret = key_file.read_bytes()
        if len(self.secret) != 32:
            raise ValueError("Invalid storage signing key")

    def check_volume(self):
        if self.expected_uuid is None:
            return
        import subprocess

        candidate = self.root
        while not candidate.exists():
            candidate = candidate.parent
        source = subprocess.run(
            ["findmnt", "-rn", "-T", str(candidate), "-o", "SOURCE"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        device = Path("/dev/disk/by-uuid") / self.expected_uuid
        if not device.exists() or Path(source).resolve() != device.resolve():
            raise ValueError("Selected storage volume is not mounted")

    def path(self, key):
        self.check_volume()
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise ValueError("Unsafe storage key")
        root = self.metadata_root if self.metadata_root is not None and key.startswith("metadata/") else self.root
        path = root / key
        if path.resolve() != path or root not in path.parents:
            raise ValueError("Storage symlinks are forbidden")
        return path

    def inventory(self):
        self.check_volume()
        total = 0
        for root in [self.root] + (
            [self.metadata_root]
            if self.metadata_root is not None and not self.metadata_root.is_relative_to(self.root)
            else []
        ):
            for path in root.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Storage contains a symlink")
                if path.is_file():
                    total += path.stat().st_size
        return total

    def get(self, key):
        with self.path(key).open("rb") as stream:
            while chunk := stream.read(1024**2):
                yield chunk

    def read_version(self, key):
        path = self.path(key)
        # Uploads are published once and cannot be overwritten by upload rights.
        return digest(path), self.get(key)

    def publish_upload(self, source, destination, etag):
        source_path, target = self.path(source), self.path(destination)
        if digest(source_path) != etag or destination != "objects/" + etag:
            raise ValueError("Verified upload changed before publication")
        self._publish(target, self.get(source), etag)
        source_path.unlink()

    def _publish(self, target, chunks, expected=None):
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=target.parent)
        temporary = Path(temporary)
        actual = hashlib.sha256()
        try:
            with os.fdopen(fd, "wb") as stream:
                for chunk in chunks:
                    actual.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if expected is not None and actual.hexdigest() != expected:
                raise ValueError("Publication hash mismatch")
            try:
                os.link(temporary, target)
            except FileExistsError:
                if digest(target) != actual.hexdigest():
                    raise ValueError("Immutable object already has different contents")
        finally:
            temporary.unlink(missing_ok=True)

    def put(self, key, data):
        self._publish(self.path(key), [data])

    def put_file(self, key, source, expected=None):
        """Publish a large local file under `key` without reading it into memory."""

        def chunks():
            with open(source, "rb") as stream:
                while chunk := stream.read(1024**2):
                    yield chunk

        self._publish(self.path(key), chunks(), expected)

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)

    def _token(self, method, key, size, lifetime):
        self.path(key)
        payload = json.dumps(
            {"method": method, "key": key, "size": size, "expires": int(time.time()) + lifetime}, sort_keys=True
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
        return encoded + "." + hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()

    def _url(self, method, key, size, lifetime):
        return self.base_url + "/api/v1/local-storage/" + self._token(method, key, size, lifetime)

    def public_study_url(self, public_base, key):
        """A dataset object for a device without the private route (owner decision 2026-10-22): over the lab's public
        HTTPS address, for 5 minutes, only for objects up to PUBLIC_STUDY_MAX_BYTES. Model weights never qualify."""
        path = self.path(key)
        if not key.startswith("objects/") or not path.is_file() or path.stat().st_size > PUBLIC_STUDY_MAX_BYTES:
            return None
        return public_base.rstrip("/") + "/api/v1/public-study/" + self._token("GET-PUBLIC", key, None, 300)

    def grant(self, token, method):
        try:
            encoded, signature = token.split(".")
            expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("Invalid signature")
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if payload["method"] != method or payload["expires"] <= time.time():
                raise ValueError("Wrong method or expired capability")
            self.path(payload["key"])
            return payload
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(403, "Invalid or expired storage capability") from None

    def upload_plan(self, key, size):
        if not key.startswith("uploads/") or type(size) is not int or not 0 < size <= 5_000_000_000:
            raise ValueError("Invalid upload size or key")
        return {
            "mode": "single",
            "key": key,
            "url": self._url("PUT", key, size, 900),
            "headers": {"Content-Length": str(size)},
        }

    def download_url(self, key):
        return self._url("GET", key, None, 60)

    def _open_upload(self, session, token, content_length):
        with session.lock:
            if session.closed:
                raise RuntimeError("Upload already closed")
            grant = self.grant(token, "PUT")
            if content_length != str(grant["size"]):
                raise HTTPException(400, "Signed upload length required")
            if shutil.disk_usage(self.root).free < grant["size"] + 64 * 1024**2:
                raise HTTPException(507, "Local storage is full")
            session.open(self.path(grant["key"]), grant["size"])

    def install_routes(self, app):
        @app.put("/api/v1/local-storage/{token}")
        async def upload(token: str, request: Request):
            session = _Upload()
            try:
                await run_in_threadpool(self._open_upload, session, token, request.headers.get("content-length"))
                async for chunk in request.stream():
                    await run_in_threadpool(session.write, chunk)
                return await run_in_threadpool(session.finish)
            finally:
                with CancelScope(shield=True):
                    await run_in_threadpool(session.close)

        @app.get("/api/v1/public-study/{token}")
        def public_study(token: str):
            grant = self.grant(token, "GET-PUBLIC")
            path = self.path(grant["key"])
            if not path.is_file() or path.stat().st_size > PUBLIC_STUDY_MAX_BYTES:
                raise HTTPException(404, "Object unavailable")
            return FileResponse(path, media_type="application/octet-stream")

        @app.get("/api/v1/local-storage/{token}")
        def download(token: str):
            grant = self.grant(token, "GET")
            path = self.path(grant["key"])
            if not path.is_file():
                raise HTTPException(404, "Object unavailable")
            return FileResponse(path, media_type="application/octet-stream")
