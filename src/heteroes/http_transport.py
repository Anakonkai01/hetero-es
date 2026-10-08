"""
The worker protocol over HTTP, with the standard library only (no new dependency on the coordinator or on the workers).

`CoordinatorServer` carries the messages of `heteroes.worker_api.WorkerAPI` and serves two more things. `HttpClient` is the
transport of a `heteroes.worker.WorkerClient`, plus what a worker needs besides leases.

    POST /v1/leases    {"worker_id"}                              -> WorkerAPI "lease"
    POST /v1/results   {"descriptor", "attempt_number", ...}      -> WorkerAPI "submit_result"
    POST /v1/failures  {"descriptor", "attempt_number", ...}      -> WorkerAPI "report_failure"
    GET  /v1/health                                               -> {"ok": true, "status": "up"}
    GET  /v1/job                                                  -> {"ok": true, "job": {...}}   what this generation is (recipe, parent weights)
    GET  /v1/models/{sha256}                                      -> the weights file published under that hash (data plane)
    GET  /v1/updates/{sha256}                                     -> {"ok": true, "update": {...}}  the update that turned the weights with that hash
                                                                     into their child (a few hundred bytes: the record, its hash, the child's hash); 404 if none

HTTP status: 200 for an ok reply, 400 bad request, 401 wrong or missing token, 404 and 405 for what does not exist, 409 for a
refusal of the ledger (the body has the code), 413 for a body that is too large, 500 for a bug of the coordinator (kept in
`internal_errors`; the server keeps serving). The body of every reply is the same JSON as without HTTP.

    POST /v1/heartbeats {"descriptor", "attempt_number", "token"}     -> WorkerAPI "heartbeat" (keeps a lease alive)

The client does not give up at the first network error for what is idempotent (a result, a failure report, a heartbeat: the
ledger acknowledges a repeat) and for a lease that carries a `request_id` (the coordinator gives the same lease back for a repeated
id); a lease without an id is never repeated, because a lost answer would give the worker a second candidate.
The token is an optional shared secret (header `Authorization: Bearer ...`), not an identity: workers are trusted, the
network is a private one (LAN or Tailscale), and the lease token of every attempt is what a result has to bring back. A wrong or
missing token is an `UnauthorizedError` (a kind of `TransportError`) that the worker can stop on at once. The server refuses to
listen on a non-loopback address without a token unless `allow_unauthenticated=True` is given: the token travels in clear text, so
the network must still be private, but a forgotten token must not mean an open coordinator.

A client that stalls is disconnected after `request_timeout` seconds and at most `max_connections` connections are served at once
(the others are closed at once and retry): a stalled or hostile peer cannot pin the server's threads for ever. The weights file
is served with `Accept-Ranges: bytes` and `Range: bytes=N-` is honoured (206), so that a broken download can continue.
"""
import hmac
import http.client
import http.server
import json
import re
import socket
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

MAX_BODY_BYTES = 1 << 20
CHUNK_BYTES = 1 << 20
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ROUTES = {"/v1/leases": "lease", "/v1/results": "submit_result", "/v1/failures": "report_failure", "/v1/heartbeats": "heartbeat"}
_ROUTE_OF = {operation: route for route, operation in _ROUTES.items()}
_IDEMPOTENT = {"submit_result", "report_failure", "heartbeat"}
_RANGE = re.compile(r"bytes=(\d+)-")
_LOOPBACK = ("localhost", "::1")
DEFAULT_REQUEST_TIMEOUT = 60.0
DEFAULT_MAX_CONNECTIONS = 64
_ANSWERED = object()      # `_read_json` has already sent the error (None is a valid JSON body)


class TransportError(ConnectionError):
    """The coordinator could not be reached, did not answer in time, or did not answer with JSON."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class UnauthorizedError(TransportError):
    """The coordinator refused the token (missing or wrong): retrying cannot help, the worker should stop and say so."""


def _is_loopback(host: str) -> bool:
    return host in _LOOPBACK or host.startswith("127.")


def _status_of(reply: dict) -> int:
    if reply.get("ok") is True:
        return 200
    code = reply.get("error", {}).get("code")
    return 400 if code == "bad_request" else 409


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "HeteroES"

    def log_message(self, *args):
        pass

    @property
    def coordinator(self) -> "CoordinatorServer":
        return self.server.coordinator

    def _reply(self, status: int, reply: dict) -> None:
        body = json.dumps(reply).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._reply(status, {"ok": False, "error": {"code": code, "message": message}})

    def send_error(self, code, message=None, explain=None):
        self._error(code, "bad_request" if code < 500 else "internal_error", message or "error")

    def _authorized(self) -> bool:
        token = self.coordinator.token
        if token is None:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer ") and hmac.compare_digest(header[len("Bearer "):].encode(), token.encode()):
            return True
        self._error(401, "unauthorized", "missing or wrong token")
        return False

    def _read_json(self):
        """The JSON body, or _ANSWERED after having sent the error."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0:
            self._error(400, "bad_request", "the request needs a valid Content-Length")
            return _ANSWERED
        if length > MAX_BODY_BYTES:
            self._error(413, "bad_request", f"the body is larger than {MAX_BODY_BYTES} bytes")
            return _ANSWERED
        try:
            return json.loads(self.rfile.read(length))
        except ValueError as error:                  # includes a body that is not valid UTF-8
            self._error(400, "bad_request", f"the body is not JSON: {error}")
            return _ANSWERED

    def do_GET(self):
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        if path == "/v1/health":
            self._reply(200, {"ok": True, "status": "up"})
        elif path == "/v1/job":
            self._reply(200, {"ok": True, "job": self.coordinator.job})
        elif path.startswith("/v1/models/"):
            self._serve_model(path[len("/v1/models/"):])
        elif path.startswith("/v1/updates/"):
            self._serve_update(path[len("/v1/updates/"):])
        elif path in _ROUTES:
            self._error(405, "bad_request", "use POST")
        else:
            self._error(404, "unknown_operation", f"no such route: {path}")

    def do_POST(self):
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        if path not in _ROUTES:
            known = path in ("/v1/health", "/v1/job") or path.startswith(("/v1/models/", "/v1/updates/"))
            self._error(405 if known else 404, "bad_request" if known else "unknown_operation",
                        "use GET" if known else f"no such route: {path}")
            return
        request = self._read_json()
        if request is _ANSWERED:
            return
        try:
            reply = self.coordinator.api.handle(_ROUTES[path], request)
        except Exception as error:                   # a bug of the coordinator: say so, keep the server alive
            self.coordinator.internal_errors.append(f"{type(error).__name__}: {error}\n{traceback.format_exc()}")
            self._error(500, "internal_error", f"{type(error).__name__}: {error}")
            return
        self._reply(_status_of(reply), reply)

    def _method_not_allowed(self):
        if self._authorized():
            self._error(405, "bad_request", f"method {self.command} is not allowed")

    do_PUT = do_DELETE = do_PATCH = _method_not_allowed

    def _serve_update(self, name: str) -> None:
        update = self.coordinator.updates.get(name) if _HEX64.fullmatch(name) else None
        if update is None:
            self._error(404, "unknown_operation", "no such update")
            return
        self._reply(200, {"ok": True, "update": update})

    def _serve_model(self, name: str) -> None:
        directory = self.coordinator.models_dir
        path = None if directory is None or not _HEX64.fullmatch(name) else directory / f"{name}.bin"
        if path is None or not path.is_file():
            self._error(404, "unknown_operation", "no such model")
            return
        size = path.stat().st_size
        start, status = 0, 200
        match = _RANGE.fullmatch(self.headers.get("Range", "").strip())
        if match and int(match.group(1)) > 0:               # only "bytes=N-" is supported; any other form gets the whole file
            start = int(match.group(1))
            if start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size - start))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
        self.end_headers()
        try:
            with open(path, "rb") as file:
                file.seek(start)
                while chunk := file.read(CHUNK_BYTES):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout):
            pass                                     # the worker went away or stalled: its business


class _BoundedServer(http.server.ThreadingHTTPServer):
    """One thread per connection, at most `max_connections` at once: the others are closed without an answer (the client retries)."""

    daemon_threads = True
    request_queue_size = 64

    def process_request(self, request, client_address):
        owner = self.coordinator
        if not owner._slots.acquire(blocking=False):
            owner.refused_connections += 1
            self.shutdown_request(request)
            return
        with owner._count_lock:
            owner.open_connections += 1
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        owner = self.coordinator
        try:
            super().process_request_thread(request, client_address)
        finally:
            with owner._count_lock:
                owner.open_connections -= 1
            owner._slots.release()


class CoordinatorServer:
    """
    `api` serves the leases, `job` describes the generation (JSON-able), `models_dir` holds the published weights as
    `<sha256>.bin`, `token` (optional) is the shared secret. `set_generation` moves on to the next generation.
    """

    def __init__(self, api, job: dict | None = None, models_dir=None, host: str = "127.0.0.1", port: int = 0,
                 token: str | None = None, request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
                 max_connections: int = DEFAULT_MAX_CONNECTIONS, allow_unauthenticated: bool = False):
        if isinstance(request_timeout, bool) or not isinstance(request_timeout, (int, float)) or not request_timeout > 0:
            raise ValueError(f"request_timeout must be a positive number, got {request_timeout!r}")
        if isinstance(max_connections, bool) or not isinstance(max_connections, int) or max_connections < 1:
            raise ValueError(f"max_connections must be an integer of at least 1, got {max_connections!r}")
        if token is None and not _is_loopback(host) and not allow_unauthenticated:
            raise ValueError(f"refusing to listen on {host} without a token: set one, or pass allow_unauthenticated=True "
                             f"for a network that is private by other means")
        self._lock = threading.Lock()
        self._api, self._job = api, job
        self.models_dir = None if models_dir is None else Path(models_dir)
        self.token = token
        self.request_timeout, self.max_connections = request_timeout, max_connections
        self.internal_errors: list[str] = []
        self.updates: dict[str, dict] = {}       # parent weights sha256 -> {"record_json", "record_hash", "child_weights_sha256"}: filled by whoever applies the updates
        self.open_connections = 0
        self.refused_connections = 0
        self._count_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_connections)
        handler = type("Handler", (_Handler,), {"timeout": request_timeout})     # the socket timeout of every connection
        self._httpd = _BoundedServer((host, port), handler)
        self._httpd.coordinator = self
        self.host, self.port = self._httpd.server_address[0], self._httpd.server_address[1]
        self._thread: threading.Thread | None = None

    @property
    def api(self):
        with self._lock:
            return self._api

    @property
    def job(self):
        with self._lock:
            return self._job

    def set_generation(self, api, job: dict | None) -> None:
        with self._lock:
            self._api, self._job = api, job

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=10)
            self._thread = None
        self._httpd.server_close()


class HttpClient:
    """A transport for `WorkerClient` (call it with `(operation, payload)`), and the other things a worker asks of the coordinator."""

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0, retries: int = 3, backoff: float = 0.5):
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._retries = retries
        self._backoff = backoff
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))    # a private network, never a proxy

    def _request(self, method: str, path: str, data: bytes | None = None):
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return urllib.request.Request(self._base + path, data=data, headers=headers, method=method)

    def _exchange(self, request) -> tuple[int, bytes]:
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:       # a reply with a status of 4xx or 5xx still carries its JSON
            return error.code, error.read()
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            raise TransportError(f"{request.get_method()} {request.full_url}: {error}") from error

    def _json(self, request):
        status, body = self._exchange(request)
        if status == 401:
            raise UnauthorizedError(f"{request.get_method()} {request.full_url}: HTTP 401, the token is missing or wrong", 401)
        try:
            return json.loads(body)
        except ValueError as error:
            raise TransportError(f"{request.get_method()} {request.full_url}: HTTP {status} without JSON", status) from error

    def __call__(self, operation: str, payload: dict):
        if operation not in _ROUTE_OF:
            raise ValueError(f"unknown operation {operation!r}")
        request = self._request("POST", _ROUTE_OF[operation], json.dumps(payload, allow_nan=False).encode("utf-8"))
        repeatable = operation in _IDEMPOTENT or (operation == "lease" and "request_id" in payload)
        tries = 1 + (self._retries if repeatable else 0)
        for attempt in range(tries):
            try:
                return self._json(request)
            except UnauthorizedError:
                raise
            except TransportError:
                if attempt == tries - 1:
                    raise
                time.sleep(self._backoff * 2 ** attempt)

    def get_json(self, path: str):
        return self._json(self._request("GET", path))

    def get_update(self, parent_sha256: str) -> dict | None:
        """The update that turned the weights with this hash into their child, or None if the coordinator has none (404)."""
        reply = self.get_json(f"/v1/updates/{parent_sha256}")
        if reply.get("ok") is True:
            return reply["update"]
        if reply.get("error", {}).get("code") == "unknown_operation":
            return None
        raise TransportError(f"the coordinator refused to give the update of {parent_sha256[:12]}: {reply!r}")

    def open_stream(self, path: str, start: int = 0):
        """
        The body of a GET as a file-like object (a context manager), for what is too large to read at once. With `start` > 0 it asks
        for `Range: bytes=start-`; the answer's `status` is 206 if the server honoured it and 200 if it sent the whole file.
        """
        request = self._request("GET", path)
        if start > 0:
            request.add_header("Range", f"bytes={start}-")
        try:
            return self._opener.open(request, timeout=self._timeout)
        except urllib.error.HTTPError as error:
            if error.code == 401:
                raise UnauthorizedError(f"GET {path}: HTTP 401, the token is missing or wrong", 401) from error
            raise TransportError(f"GET {path}: HTTP {error.code}", error.code) from error
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            raise TransportError(f"GET {path}: {error}") from error
