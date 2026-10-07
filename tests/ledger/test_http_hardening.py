"""
Hardening of the HTTP layer found by the audit of 07/10/2026 (G6):
  - a client that stalls cannot hold a server thread for ever (socket timeout), and the number of connections served at once is bounded;
  - a wrong or missing token is an error the worker sees at once (UnauthorizedError), not a silent loop;
  - the server refuses to listen on a non-loopback address without a token unless that is asked for explicitly;
  - the weights download can resume: the server answers `Range: bytes=N-` and the worker keeps and continues a partial file;
  - a lease request that carries a request id is retried by the client (a lost reply costs nothing).
"""
import hashlib
import http.client
import os
import socket
import threading
import time

import pytest

from heteroes.http_transport import CoordinatorServer, HttpClient, TransportError, UnauthorizedError
from heteroes.ledger import Ledger
from heteroes.model.weights_io import WeightsFileError
from heteroes.worker_api import WorkerAPI
from heteroes.worker_runtime import download_weights
from ledger_helpers import FakeClock, batch

JOB = {"experiment_id": "exp", "generation": 0, "recipe_hash": "a" * 64, "parent_weights_sha256": "b" * 64}


@pytest.fixture
def api():
    with Ledger(":memory:", clock=FakeClock()) as ledger:
        ledger.open_generation(batch(4))
        yield WorkerAPI(ledger, "exp", 0, lease_seconds=30.0)


def serve(api, tmp_path, **options):
    server = CoordinatorServer(api, job=JOB, models_dir=tmp_path, **options)
    server.start()
    return server


def slow_client(server):
    """A client that sends the start of a request and then nothing."""
    sock = socket.create_connection((server.host, server.port), timeout=10)
    sock.sendall(b"POST /v1/leases HTTP/1.1\r\nHost: x\r\nContent-Length: 100\r\n\r\n{")
    return sock


def closed_by_server(sock, within):
    sock.settimeout(within)
    try:
        return sock.recv(4096) in (b"", ) or True      # any answer (408 or an error page) or a plain close ends the connection
    except socket.timeout:
        return False
    except ConnectionResetError:
        return True


# ---------------------------------------------------------------------------
# stalled clients and the number of connections
# ---------------------------------------------------------------------------

def test_a_client_that_stalls_in_the_middle_of_a_request_is_disconnected(api, tmp_path):
    server = serve(api, tmp_path, request_timeout=0.3)
    try:
        sock = slow_client(server)
        assert closed_by_server(sock, within=5.0)
        sock.close()
        deadline = time.time() + 5
        while server.open_connections and time.time() < deadline:
            time.sleep(0.02)
        assert server.open_connections == 0                       # its thread is gone, not leaked
        assert HttpClient(server.url).get_json("/v1/health") == {"ok": True, "status": "up"}
    finally:
        server.stop()


def test_connections_over_the_limit_are_refused_and_the_server_keeps_serving(api, tmp_path):
    server = serve(api, tmp_path, request_timeout=3.0, max_connections=2)
    stalled = []
    try:
        stalled = [slow_client(server) for _ in range(2)]
        deadline = time.time() + 5
        while server.open_connections < 2 and time.time() < deadline:
            time.sleep(0.02)
        assert server.open_connections == 2                       # premise: both slots are taken
        third = socket.create_connection((server.host, server.port), timeout=5)
        third.sendall(b"GET /v1/health HTTP/1.1\r\nHost: x\r\n\r\n")
        third.settimeout(2.0)
        try:
            data = third.recv(4096)
        except ConnectionResetError:
            data = b""
        third.close()
        assert data == b""                                        # refused: closed without an answer
        assert server.refused_connections >= 1
    finally:
        for sock in stalled:
            sock.close()
        deadline = time.time() + 6
        while server.open_connections and time.time() < deadline:
            time.sleep(0.05)
        try:
            assert HttpClient(server.url).get_json("/v1/health")["ok"] is True       # after the slots are free again it works
        finally:
            server.stop()


def test_the_default_limits_are_reasonable(api, tmp_path):
    server = serve(api, tmp_path)
    try:
        assert 5 <= server.request_timeout <= 120
        assert 8 <= server.max_connections <= 256
    finally:
        server.stop()


@pytest.mark.parametrize("name,bad", [("request_timeout", 0), ("request_timeout", -1), ("max_connections", 0), ("max_connections", 1.5)])
def test_bad_limits_are_refused(api, tmp_path, name, bad):
    with pytest.raises(ValueError):
        CoordinatorServer(api, job=JOB, models_dir=tmp_path, **{name: bad})


# ---------------------------------------------------------------------------
# token
# ---------------------------------------------------------------------------

@pytest.fixture
def guarded(api, tmp_path):
    server = serve(api, tmp_path, token="s3cret")
    yield server
    server.stop()


@pytest.mark.parametrize("token", [None, "wrong"])
def test_a_wrong_or_missing_token_is_an_unauthorized_error_on_every_kind_of_call(guarded, token):
    client = HttpClient(guarded.url, token=token)
    with pytest.raises(UnauthorizedError):
        client.get_json("/v1/job")
    with pytest.raises(UnauthorizedError):
        client("lease", {"worker_id": "worker-a"})
    with pytest.raises(UnauthorizedError):
        client.open_stream("/v1/models/" + "a" * 64)
    assert issubclass(UnauthorizedError, TransportError)          # old code that catches TransportError still catches it


def test_the_right_token_is_not_an_error(guarded):
    assert HttpClient(guarded.url, token="s3cret").get_json("/v1/health")["ok"] is True


def test_a_non_loopback_address_without_a_token_is_refused_unless_asked_for(api, tmp_path):
    with pytest.raises(ValueError, match="token"):
        CoordinatorServer(api, job=JOB, models_dir=tmp_path, host="0.0.0.0")
    server = CoordinatorServer(api, job=JOB, models_dir=tmp_path, host="0.0.0.0", allow_unauthenticated=True)
    server.stop()
    server = CoordinatorServer(api, job=JOB, models_dir=tmp_path, host="0.0.0.0", token="x")
    server.stop()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_needs_no_token(api, tmp_path, host):
    try:
        server = CoordinatorServer(api, job=JOB, models_dir=tmp_path, host=host)
    except OSError:
        pytest.skip(f"{host} is not available here")
    server.stop()


# ---------------------------------------------------------------------------
# ranges
# ---------------------------------------------------------------------------

DATA = bytes(range(256)) * 40                                      # 10,240 bytes with no repeats inside a block
SHA = hashlib.sha256(DATA).hexdigest()


@pytest.fixture
def with_file(api, tmp_path):
    (tmp_path / f"{SHA}.bin").write_bytes(DATA)
    server = serve(api, tmp_path)
    yield server
    server.stop()


def raw_get(server, headers):
    connection = http.client.HTTPConnection(server.host, server.port, timeout=10)
    try:
        connection.request("GET", f"/v1/models/{SHA}", headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_a_range_from_an_offset_gets_the_rest_of_the_file_with_206(with_file):
    status, headers, body = raw_get(with_file, {"Range": "bytes=1000-"})
    assert status == 206 and body == DATA[1000:]
    assert headers["Content-Range"] == f"bytes 1000-{len(DATA) - 1}/{len(DATA)}"
    assert int(headers["Content-Length"]) == len(DATA) - 1000


def test_a_range_from_zero_and_no_range_both_give_the_whole_file(with_file):
    assert raw_get(with_file, {})[2] == DATA
    status, _, body = raw_get(with_file, {"Range": "bytes=0-"})
    assert status in (200, 206) and body == DATA


def test_a_range_at_the_end_of_the_file_is_not_satisfiable(with_file):
    status, headers, _ = raw_get(with_file, {"Range": f"bytes={len(DATA)}-"})
    assert status == 416 and headers["Content-Range"] == f"bytes */{len(DATA)}"
    assert raw_get(with_file, {"Range": f"bytes={len(DATA) + 5}-"})[0] == 416


@pytest.mark.parametrize("header", ["bytes=-100", "bytes=0-99", "bytes=1-2,5-6", "items=3-", "bytes=abc-", "garbage"])
def test_a_range_the_server_does_not_support_gets_the_whole_file(with_file, header):
    status, _, body = raw_get(with_file, {"Range": header})
    assert status == 200 and body == DATA                         # the client sees 200 and starts again from zero: always correct


def test_the_response_to_a_normal_request_says_that_ranges_are_accepted(with_file):
    assert raw_get(with_file, {})[1].get("Accept-Ranges") == "bytes"


def test_the_client_can_open_a_stream_from_an_offset(with_file):
    with HttpClient(with_file.url).open_stream(f"/v1/models/{SHA}", start=5000) as response:
        assert response.status == 206 and response.read() == DATA[5000:]


# ---------------------------------------------------------------------------
# a resumable download
# ---------------------------------------------------------------------------

class CuttingClient:
    """An HttpClient whose first stream breaks after `cut` bytes (a cable pulled), the later ones are whole."""

    def __init__(self, real, cut):
        self.real, self.cut, self.streams, self.bytes_asked = real, cut, [], 0

    def open_stream(self, path, start=0):
        self.streams.append(start)
        response = self.real.open_stream(path, start=start)
        if len(self.streams) > 1:
            return response
        return _CutResponse(response, self.cut)


class _CutResponse:
    def __init__(self, response, cut):
        self.response, self.left = response, cut

    def __enter__(self):
        self.response.__enter__()
        return self

    def __exit__(self, *exc):
        return self.response.__exit__(*exc)

    def read(self, n):
        if self.left <= 0:
            raise http.client.IncompleteRead(b"")
        data = self.response.read(min(n, self.left))
        self.left -= len(data)
        return data


def test_a_broken_download_resumes_from_what_arrived_and_the_result_is_verified(with_file, tmp_path):
    cache = tmp_path / "cache"
    client = CuttingClient(HttpClient(with_file.url), cut=3000)
    with pytest.raises(TransportError):
        download_weights(client, SHA, cache, chunk_bytes=512)
    partials = [p for p in cache.iterdir()]
    assert len(partials) == 1 and 0 < partials[0].stat().st_size <= 3000       # the first bytes are kept, nothing else is left
    assert not (cache / f"{SHA}.bin").exists()                                  # and the file does not look finished

    path = download_weights(client, SHA, cache, chunk_bytes=512)

    assert path.read_bytes() == DATA
    assert client.streams[0] == 0 and client.streams[1] > 0                     # the second request began where the first stopped
    assert sorted(p.name for p in cache.iterdir()) == [f"{SHA}.bin"]


def test_a_partial_file_that_is_longer_than_the_file_or_wrong_is_discarded_not_trusted(with_file, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / f".partial-{SHA}").write_bytes(b"x" * 20_000)                     # more than the real size
    client = CuttingClient(HttpClient(with_file.url), cut=10**9)
    assert download_weights(client, SHA, cache).read_bytes() == DATA

    (cache / f".partial-{SHA}").write_bytes(b"this is not the beginning of the weights")
    cache2 = tmp_path / "cache2"
    cache2.mkdir()
    (cache2 / f".partial-{SHA}").write_bytes(b"this is not the beginning of the weights")
    with pytest.raises(WeightsFileError):
        download_weights(CuttingClient(HttpClient(with_file.url), cut=10**9), SHA, cache2)    # the wrong prefix is caught by the hash
    assert list(cache2.iterdir()) == []                                          # and a prefix that gave a wrong hash is not kept


def test_a_server_that_ignores_the_range_makes_the_download_start_again(tmp_path, api):
    (tmp_path / f"{SHA}.bin").write_bytes(DATA)
    server = serve(api, tmp_path)
    try:
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / f".partial-{SHA}").write_bytes(DATA[:4000])

        class NoRange(HttpClient):
            def open_stream(self, path, start=0):
                return super().open_stream(path, start=0)                       # an old server: always the whole file, status 200

        assert download_weights(NoRange(server.url), SHA, cache).read_bytes() == DATA
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# repeating a lease request
# ---------------------------------------------------------------------------

def test_a_lease_with_a_request_id_is_retried_after_a_lost_answer_and_gives_one_lease(api, tmp_path):
    server = serve(api, tmp_path)
    try:
        client = HttpClient(server.url, retries=3, backoff=0.01)
        real = client._exchange
        state = {"calls": 0}

        def lose_the_first_answer(request):
            result = real(request)                                   # the server did handle it ...
            state["calls"] += 1
            if state["calls"] == 1:
                raise TransportError("the answer was lost")          # ... but the worker never saw the answer
            return result

        client._exchange = lose_the_first_answer
        reply = client("lease", {"worker_id": "worker-a", "request_id": "r1"})

        assert state["calls"] == 2 and reply["ok"] is True and reply["work"]["descriptor"]["index"] == 0
        taken = [r.attempts for r in api._ledger.list_candidates("exp", 0)]
        assert taken == [1, 0, 0, 0]                                 # ONE candidate leased, not two
    finally:
        server.stop()


def test_a_lease_without_a_request_id_is_still_never_retried(api, tmp_path):
    server = serve(api, tmp_path)
    try:
        client = HttpClient(server.url, retries=3, backoff=0.01)

        def fail(request):
            raise TransportError("down")

        client._exchange = fail
        with pytest.raises(TransportError):
            client("lease", {"worker_id": "worker-a"})
    finally:
        server.stop()


def test_a_partial_file_that_is_already_the_whole_file_is_finished_without_downloading_it_again(with_file, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / f".partial-{SHA}").write_bytes(DATA)                            # everything arrived, the process died before the rename
    client = CuttingClient(HttpClient(with_file.url), cut=10**9)

    path = download_weights(client, SHA, cache)

    assert path.read_bytes() == DATA and client.streams == [len(DATA)]       # one request (answered 416): nothing was transferred again
    assert sorted(p.name for p in cache.iterdir()) == [f"{SHA}.bin"]
