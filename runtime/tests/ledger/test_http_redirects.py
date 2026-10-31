"""Real HTTP redirects must never forward credentials or private transfers to a second origin."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import threading
from types import SimpleNamespace
import urllib.request

import pytest

from heteroes.http_transport import HttpClient
from heteroes.product import agent_protocol, cloud_sync, connection, downloads, worker_cli, worker_lab
from heteroes import sdk_lab
from heteroes.study import prepare
from heteroes.v3 import lab_cli


@pytest.fixture
def origins():
    received = []

    class Destination(BaseHTTPRequestHandler):
        def consume_body(self):
            if self.headers.get("Transfer-Encoding") == "chunked":
                while size := int(self.rfile.readline().strip(), 16):
                    self.rfile.read(size + 2)
                self.rfile.readline()
            else:
                self.rfile.read(int(self.headers.get("Content-Length", "0")))

        def handle_request(self):
            self.consume_body()
            received.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        do_GET = do_POST = do_PUT = handle_request

        def log_message(self, *args):
            pass

    target = ThreadingHTTPServer(("127.0.0.1", 0), Destination)
    destination = f"http://127.0.0.1:{target.server_port}"
    state = {"status": 302, "location": destination + "/sensitive?capability=synthetic-secret", "requests": []}

    class Redirect(Destination):
        def handle_request(self):
            self.consume_body()
            state["requests"].append(self.path)
            self.send_response(state["status"])
            self.send_header("Location", state["location"])
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = do_PUT = handle_request

    source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threads = [threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.01}) for s in (source, target)]
    for thread in threads:
        thread.start()
    try:
        yield f"http://127.0.0.1:{source.server_port}", destination, received, state
    finally:
        for server in (source, target):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()


CALLS = [
    "compute-json",
    "compute-post",
    "compute-stream",
    "agent",
    "reachable",
    "connection",
    "worker-request",
    "worker-health",
    "worker-update",
    "cloud-put",
    "download",
    "sdk-request",
    "sdk-upload",
    "cli-request",
    "cli-upload",
    "study-transfer",
]


def invoke(name, origin, tmp_path, monkeypatch):
    token = "synthetic-bearer"
    headers = {"Authorization": "Bearer " + token}
    path = tmp_path / "upload"
    path.write_bytes(b"payload")
    plan = {"url": origin + "/upload", "headers": headers}
    if name.startswith("compute-"):
        client = HttpClient(origin, token=token, retries=0)
        if name == "compute-json":
            return client.get_json("/v1/job")
        if name == "compute-post":
            return client("lease", {"worker_id": "w"})
        return client.open_stream("/v1/models/" + "a" * 64)
    if name == "agent":
        return agent_protocol.request(origin, "/api/v1/device/poll", token, {})
    if name == "reachable":
        return agent_protocol.reachable(origin, token)
    if name == "connection":
        return connection.check_worker({"coordinatorUrl": origin, "computeToken": token})
    if name == "worker-request":
        return worker_lab.lab_request(origin, "/api/v1/device/poll", token, {})
    if name == "worker-health":
        return worker_lab.lab_health(origin)
    if name == "worker-update":
        worker = SimpleNamespace(settings=lambda: {"serverUrl": origin}, paths=lambda: {"runtime": path})
        return worker_cli.update(worker, SimpleNamespace(force=True))
    if name == "cloud-put":
        return cloud_sync.CloudSync(None)._put(
            origin + "/object", io.BytesIO(b"payload"), 0, 7, hashlib.sha256(), headers
        )
    if name == "download":
        return downloads.verified_download(
            {
                "name": "bundle",
                "url": origin + "/bundle",
                "sizeBytes": 7,
                "sha256": hashlib.sha256(b"payload").hexdigest(),
            },
            tmp_path / "downloads",
            say=lambda _: None,
            attempts=1,
        )
    if name == "sdk-request":
        return sdk_lab.Lab(origin, token, "workspace").request("GET", "/api/v1/workers", retries=1)
    if name == "sdk-upload":
        return sdk_lab.Lab(origin, token, "workspace").upload(plan, path)
    if name in ("cli-request", "cli-upload"):
        monkeypatch.setenv("HETEROES_LAB_ACCESS_TOKEN", token)
        lab = lab_cli.Lab(origin, "workspace")
        return lab.request("GET", "/api/v1/workers") if name == "cli-request" else lab.upload(plan, path)
    agent = SimpleNamespace(call=lambda *args: {"url": origin + "/study?capability=synthetic-secret"})
    return prepare.transfer(agent, {"jobId": "j"}, "a" * 64, tmp_path / "dataset", 100)


@pytest.mark.parametrize("name", CALLS)
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_every_client_blocks_redirects(name, status, origins, tmp_path, monkeypatch):
    origin, destination, received, state = origins
    state["status"] = status
    if name in ("reachable", "connection"):
        value = invoke(name, origin, tmp_path, monkeypatch)
        assert value is False if name == "reachable" else value["route"] is None
    else:
        with pytest.raises(Exception) as caught:
            invoke(name, origin, tmp_path, monkeypatch)
        message = str(caught.value)
        assert "redirect" in message.lower() and destination in message and "final URL" in message
        assert "synthetic-secret" not in message and "synthetic-bearer" not in message
    assert state["requests"], "The source must actually be contacted"
    assert received == [], "The redirect destination must not receive even one request"


@pytest.mark.parametrize("status", [300, 304, 305, 306, 399])
def test_other_3xx_are_also_rejected(status, origins):
    from heteroes.http_safety import RedirectError, opener

    origin, _, received, state = origins
    state["status"] = status
    with pytest.raises(RedirectError):
        opener(proxy=False).open(origin)
    assert received == []


@pytest.mark.parametrize(
    "location", ["/relative?secret=hidden", "http://user:password@localhost:1234/a?secret=hidden", "http://["]
)
def test_error_contains_only_a_safe_origin(location, origins):
    from heteroes.http_safety import RedirectError, opener

    origin, _, received, state = origins
    state["location"] = location
    with pytest.raises(RedirectError) as caught:
        opener(proxy=False).open(origin)
    assert "hidden" not in str(caught.value) and "password" not in str(caught.value)
    assert received == []


def test_worker_opener_ignores_environment_proxy_but_sdk_keeps_it(monkeypatch, origins):
    from heteroes.http_safety import opener

    origin, _, _, state = origins
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"http": origin})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    private = opener(proxy=False)
    public = opener(proxy=True)
    assert not any(isinstance(h, urllib.request.ProxyHandler) for h in private.handlers)
    assert any(isinstance(h, urllib.request.ProxyHandler) and h.proxies == {"http": origin} for h in public.handlers)
    with pytest.raises(Exception, match="redirect"):
        public.open("http://researcher.invalid/api")
    assert state["requests"] == ["http://researcher.invalid/api"]


@pytest.mark.parametrize("name", CALLS)
def test_each_callsite_uses_its_intended_proxy_policy(name, origins, tmp_path, monkeypatch):
    origin, destination, received, state = origins
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"http": destination})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    if name in ("sdk-request", "sdk-upload", "cli-request", "cli-upload"):
        invoke(name, origin, tmp_path, monkeypatch)
        assert received and received[0][0].startswith(origin)
        assert state["requests"] == []
    else:
        if name in ("reachable", "connection"):
            invoke(name, origin, tmp_path, monkeypatch)
        else:
            with pytest.raises(Exception, match="redirect"):
                invoke(name, origin, tmp_path, monkeypatch)
        assert state["requests"]
        assert received == []
