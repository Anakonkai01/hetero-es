"""
The worker protocol over real HTTP (standard library only), on localhost, with real threads.

`CoordinatorServer` wraps a `WorkerAPI`; `HttpClient` is the transport a `WorkerClient` uses. The protocol itself (messages,
error codes) is tested in test_worker_api.py: here it is the carrying that is checked: the routes, the HTTP status of every kind
of reply, bad bodies, the optional token, the model download (data plane), network errors, and a whole generation done by
workers that run in their own threads and talk to the server through sockets.
"""
import http.client
import http.server
import json
import socket
import threading
import time
import urllib.parse

import pytest

from heteroes.generation_record import GenerationRecord
from heteroes.http_transport import CoordinatorServer, HttpClient, TransportError
from heteroes.ledger import FailureKind, GenerationState, Ledger, UpdateOutcome
from heteroes.manifest import derive_seed
from heteroes.worker import CandidateFailed, Step, StepKind, Worker, WorkerAPIError, WorkerClient
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, batch, descriptor_of, make

LEASE_SECONDS = 30.0
JOB = {"experiment_id": "exp", "generation": 0, "recipe_hash": "a" * 64, "parent_weights_sha256": "b" * 64}


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as ledger:
        ledger.open_generation(batch(4))
        yield ledger


@pytest.fixture
def api(ledger):
    return WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS)


@pytest.fixture
def server(api, tmp_path):
    server = CoordinatorServer(api, job=JOB, models_dir=tmp_path)
    server.start()
    yield server
    server.stop()


def raw(server, method, path, body=None, headers=None):
    """One HTTP exchange with no help from HttpClient: (status, content type, body bytes)."""
    connection = http.client.HTTPConnection(server.host, server.port, timeout=10)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        connection.close()


def post(server, path, payload, headers=None):
    body = json.dumps(payload).encode()
    status, content_type, data = raw(server, "POST", path, body, {"Content-Type": "application/json", **(headers or {})})
    return status, content_type, json.loads(data)


def lease_over_http(server, worker="worker-a"):
    status, _, reply = post(server, "/v1/leases", {"worker_id": worker})
    assert status == 200 and reply["ok"] is True and reply["work"] is not None, reply
    return reply["work"]


# ---------------------------------------------------------------------------
# the routes and the HTTP status of every kind of reply
# ---------------------------------------------------------------------------

def test_the_server_answers_health_and_describes_the_job(server):
    assert json.loads(raw(server, "GET", "/v1/health")[2]) == {"ok": True, "status": "up"}

    status, content_type, body = raw(server, "GET", "/v1/job")

    assert status == 200 and content_type == "application/json"
    assert json.loads(body) == {"ok": True, "job": JOB}


def test_a_lease_a_result_and_a_failure_go_through_their_routes(server, ledger):
    work = lease_over_http(server)
    assert work["descriptor"] == descriptor_of(0).to_dict()

    status, content_type, reply = post(server, "/v1/results", {
        "descriptor": work["descriptor"], "attempt_number": 1, "token": work["token"], "reward": 0.5})
    assert (status, content_type, reply) == (200, "application/json", {"ok": True, "outcome": "COMMITTED"})

    other = lease_over_http(server, "worker-b")
    status, _, reply = post(server, "/v1/failures", {
        "descriptor": other["descriptor"], "attempt_number": 1, "token": other["token"], "kind": "OUT_OF_MEMORY"})
    assert (status, reply) == (200, {"ok": True})
    assert ledger.get_candidate("exp/g0/c0").result.reward == 0.5
    assert ledger.get_candidate("exp/g0/c1").state.name == "PENDING"


@pytest.mark.parametrize("path, payload, status, code", [
    ("/v1/leases", {"worker_id": ""}, 400, "bad_request"),
    ("/v1/leases", {"worker_id": "a", "duration": 5}, 400, "bad_request"),
    ("/v1/results", {"descriptor": None, "attempt_number": 1, "token": "x", "reward": 0.5}, 400, "bad_request"),
])
def test_a_malformed_request_is_a_400_with_its_code(server, ledger, path, payload, status, code):
    got_status, content_type, reply = post(server, path, payload)

    assert (got_status, content_type) == (status, "application/json")
    assert reply["ok"] is False and reply["error"]["code"] == code
    assert ledger.get_candidate("exp/g0/c0").attempts == 0


def test_a_refusal_of_the_ledger_is_a_409_with_its_code(server):
    work = lease_over_http(server)

    status, _, reply = post(server, "/v1/results", {
        "descriptor": work["descriptor"], "attempt_number": 1, "token": "0" * 32, "reward": 0.5})

    assert status == 409 and reply["error"]["code"] == "stale_attempt"


def test_a_quarantined_worker_is_refused_with_409(server):
    work = lease_over_http(server)
    post(server, "/v1/failures", {"descriptor": work["descriptor"], "attempt_number": 1, "token": work["token"],
                                  "kind": "RESTORE_MISMATCH"})

    status, _, reply = post(server, "/v1/leases", {"worker_id": "worker-a"})

    assert status == 409 and reply["error"]["code"] == "worker_quarantined"


@pytest.mark.parametrize("method, path, expected", [
    ("GET", "/nope", 404), ("POST", "/v1/nope", 404), ("GET", "/v1/models/xyz", 404), ("GET", "/", 404),
    ("POST", "/v1/health", 405), ("POST", "/v1/job", 405), ("POST", "/v1/models/" + "c" * 64, 405),
    ("GET", "/v1/leases", 405), ("GET", "/v1/results", 405), ("PUT", "/v1/leases", 405), ("DELETE", "/v1/job", 405),
    ("PATCH", "/v1/results", 405)])
def test_an_unknown_route_is_a_404_and_a_wrong_method_a_405_both_with_a_json_error(server, method, path, expected):
    status, content_type, body = raw(server, method, path, b"{}" if method in ("POST", "PUT", "PATCH") else None)

    assert status == expected and content_type == "application/json"
    assert json.loads(body)["ok"] is False


def test_a_query_string_does_not_change_the_route(server, ledger):
    assert raw(server, "GET", "/v1/health?probe=1")[0] == 200
    status, _, body = raw(server, "POST", "/v1/leases?x=1", b'{"worker_id": "a"}', {"Content-Type": "application/json"})
    assert status == 200 and json.loads(body)["work"] is not None


@pytest.mark.parametrize("body", [b"", b"not json", b"[1, 2]", b'"text"', b"null", b"\xff\xfe", b'{"worker_id": "a"'])
def test_a_body_that_is_not_a_json_object_is_a_400_and_nothing_moves(server, ledger, body):
    status, _, data = raw(server, "POST", "/v1/leases", body, {"Content-Type": "application/json"})

    assert status == 400 and json.loads(data)["error"]["code"] == "bad_request"
    assert ledger.get_candidate("exp/g0/c0").attempts == 0


def test_a_body_that_is_too_large_is_refused_without_reading_it(server):
    connection = http.client.HTTPConnection(server.host, server.port, timeout=10)
    try:
        connection.putrequest("POST", "/v1/leases")
        connection.putheader("Content-Length", str(2 << 20))          # it says it is 2 MiB, and sends none of it
        connection.endheaders()
        response = connection.getresponse()
        status, body = response.status, response.read()
    finally:
        connection.close()

    assert status == 413 and json.loads(body)["error"]["code"] == "bad_request"


def test_a_body_of_exactly_the_largest_allowed_size_is_accepted_and_one_more_byte_is_not(server):
    from heteroes.http_transport import MAX_BODY_BYTES

    def padded(size):
        base = b'{"worker_id": "a"}'
        return base + b" " * (size - len(base))                      # JSON ignores trailing white space

    status, _, body = raw(server, "POST", "/v1/leases", padded(MAX_BODY_BYTES), {"Content-Type": "application/json"})
    assert status == 200 and json.loads(body)["ok"] is True

    connection = http.client.HTTPConnection(server.host, server.port, timeout=10)
    try:
        connection.putrequest("POST", "/v1/leases")
        connection.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
        connection.endheaders()
        assert connection.getresponse().status == 413
    finally:
        connection.close()


def test_a_method_the_server_does_not_know_still_gets_a_json_answer(server):
    status, content_type, body = raw(server, "OPTIONS", "/v1/leases")

    assert status >= 400 and content_type == "application/json" and json.loads(body)["ok"] is False


def test_a_request_without_a_valid_length_is_a_400(server):
    connection = http.client.HTTPConnection(server.host, server.port, timeout=10)
    try:
        connection.putrequest("POST", "/v1/leases")
        connection.putheader("Content-Length", "abc")
        connection.endheaders()
        response = connection.getresponse()
        status, body = response.status, response.read()
    finally:
        connection.close()

    assert status == 400 and json.loads(body)["error"]["code"] == "bad_request"


def test_a_bug_in_the_coordinator_is_a_500_the_server_keeps_serving_and_the_bug_is_kept(tmp_path):
    class Broken:
        def handle(self, operation, request):
            if request.get("worker_id") == "boom":
                raise RuntimeError("bug in the coordinator")
            return {"ok": True, "generation_state": "OPEN", "work": None}

    server = CoordinatorServer(Broken(), job=JOB, models_dir=tmp_path)
    server.start()
    try:
        status, _, reply = post(server, "/v1/leases", {"worker_id": "boom"})
        assert status == 500 and reply["error"]["code"] == "internal_error" and "bug in the coordinator" in reply["error"]["message"]

        assert post(server, "/v1/leases", {"worker_id": "fine"})[0] == 200
        assert len(server.internal_errors) == 1 and "bug in the coordinator" in server.internal_errors[0]
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# the optional token
# ---------------------------------------------------------------------------

@pytest.fixture
def guarded(api, tmp_path):
    server = CoordinatorServer(api, job=JOB, models_dir=tmp_path, token="s3cret")
    server.start()
    yield server
    server.stop()


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "s3cret"},
                                     {"Authorization": "Basic s3cret"}, {"Authorization": "Bearer "}, {"Authorization": "Basic  s3cret"},
                                     {"Authorization": "bearer s3cret"}, {"Authorization": "Bearer s3cret "}, {"Authorization": "Bearer s3crex"},
                                     {"Authorization": "Bearer S3CRET"}])
def test_with_a_token_every_route_refuses_a_request_without_it(guarded, ledger, headers):
    for method, path in [("GET", "/v1/health"), ("GET", "/v1/job"), ("POST", "/v1/leases"), ("GET", "/v1/models/" + "0" * 64)]:
        status, _, body = raw(guarded, method, path, b'{"worker_id": "a"}' if method == "POST" else None, headers)
        assert status == 401 and json.loads(body)["error"]["code"] == "unauthorized", (method, path)

    assert ledger.get_candidate("exp/g0/c0").attempts == 0


def test_with_the_right_token_the_server_works(guarded):
    status, _, reply = post(guarded, "/v1/leases", {"worker_id": "a"}, {"Authorization": "Bearer s3cret"})

    assert status == 200 and reply["work"]["descriptor"]["index"] == 0


def test_the_client_sends_its_token(guarded):
    good, bad = HttpClient(guarded.url, token="s3cret"), HttpClient(guarded.url, token="nope")

    assert good.get_json("/v1/health") == {"ok": True, "status": "up"}
    with pytest.raises(WorkerAPIError) as caught:
        WorkerClient("worker-a", bad).lease()
    assert caught.value.code == "unauthorized"


# ---------------------------------------------------------------------------
# the model download (data plane)
# ---------------------------------------------------------------------------

def test_a_published_model_file_is_served_byte_for_byte(server, tmp_path):
    sha = "c" * 64
    data = bytes(range(256)) * 5000                          # more than one chunk
    (tmp_path / f"{sha}.bin").write_bytes(data)

    status, content_type, body = raw(server, "GET", f"/v1/models/{sha}")

    assert status == 200 and content_type == "application/octet-stream" and body == data
    with HttpClient(server.url).open_stream(f"/v1/models/{sha}") as stream:
        assert stream.read() == data


@pytest.mark.parametrize("name", ["d" * 64, "../secret", "../" * 4 + "etc/passwd", "C" * 64, "c" * 63, "c" * 65,
                                  "%2e%2e%2fsecret", "", ("c" * 64) + "/../" + ("c" * 64)])
def test_a_model_that_is_not_published_or_not_a_hash_is_a_404(server, tmp_path, name):
    (tmp_path.parent / "secret.bin").write_bytes(b"do not serve")         # outside the directory, but with the right suffix
    (tmp_path / ("c" * 64 + ".bin")).write_bytes(b"x")

    status, content_type, body = raw(server, "GET", "/v1/models/" + urllib.parse.quote(name, safe="/%"))

    assert status == 404 and content_type == "application/json" and b"do not serve" not in body


def test_a_server_without_a_models_directory_has_no_models(api):
    server = CoordinatorServer(api, job=JOB)
    server.start()
    try:
        assert raw(server, "GET", "/v1/models/" + "c" * 64)[0] == 404
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# the next generation replaces the API and the job
# ---------------------------------------------------------------------------

def test_the_server_can_move_on_to_the_next_generation(server, ledger, clock):
    ledger.open_generation(batch(2, generation=1))
    next_api = WorkerAPI(ledger, "exp", 1, lease_seconds=LEASE_SECONDS)
    next_job = dict(JOB, generation=1, parent_weights_sha256="e" * 64)

    server.set_generation(next_api, next_job)

    assert json.loads(raw(server, "GET", "/v1/job")[2])["job"] == next_job
    assert lease_over_http(server)["descriptor"]["generation"] == 1


# ---------------------------------------------------------------------------
# HttpClient: network errors
# ---------------------------------------------------------------------------

def free_port():
    probe = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
    port = probe.server_address[1]
    probe.server_close()
    return port


def test_the_client_refuses_an_operation_it_does_not_know_and_a_number_json_cannot_carry(server):
    client = HttpClient(server.url)

    with pytest.raises(ValueError, match="unknown operation"):
        client("nope", {})
    with pytest.raises(ValueError):
        client("submit_result", {"descriptor": {}, "attempt_number": 1, "token": "x", "reward": float("nan")})


def test_a_server_that_is_not_there_is_a_transport_error():
    client = HttpClient(f"http://127.0.0.1:{free_port()}", timeout=2.0)

    with pytest.raises(TransportError):
        client("lease", {"worker_id": "a"})
    with pytest.raises(TransportError):
        client.get_json("/v1/health")
    assert issubclass(TransportError, ConnectionError)


def test_a_server_that_was_stopped_is_a_transport_error(api, tmp_path):
    server = CoordinatorServer(api, job=JOB, models_dir=tmp_path)
    server.start()
    client = HttpClient(server.url, timeout=2.0)
    assert client.get_json("/v1/health")["ok"] is True

    server.stop()
    server.stop()                                            # stopping twice is harmless

    with pytest.raises(TransportError):
        client.get_json("/v1/health")
    with pytest.raises(ConnectionRefusedError):              # the socket is closed, not merely left unserved
        socket.create_connection((server.host, server.port), timeout=2).close()


class Misbehaving(http.server.BaseHTTPRequestHandler):
    mode = "html"

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.mode == "hang":
            time.sleep(3)
            return
        body = b"<html>a proxy error page</html>" if self.mode == "html" else b"[1, 2, 3]"
        self.send_response(200 if self.mode == "list" else 502)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST


@pytest.fixture
def misbehaving():
    servers = []

    def start(mode):
        handler = type("Handler", (Misbehaving,), {"mode": mode})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("mode", ["html", "hang"])
def test_an_answer_that_is_not_json_or_does_not_come_is_a_transport_error(misbehaving, mode):
    client = HttpClient(misbehaving(mode), timeout=0.5, retries=0)

    with pytest.raises(TransportError):
        client("lease", {"worker_id": "a"})


def test_a_json_answer_of_the_wrong_shape_is_left_to_the_protocol_layer_to_refuse(misbehaving):
    client = WorkerClient("worker-a", HttpClient(misbehaving("list"), timeout=2.0))

    with pytest.raises(WorkerAPIError) as caught:
        client.lease()

    assert caught.value.code == "bad_response"


# ---------------------------------------------------------------------------
# retries: only for what is idempotent
# ---------------------------------------------------------------------------

class Flaky:
    """A real HTTP server that closes the connection without answering for the first `drop` requests of a route."""

    def __init__(self, api, drop):
        self.api, self.drop, self.seen = api, drop, {}
        flaky = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                operation = {"/v1/leases": "lease", "/v1/results": "submit_result", "/v1/failures": "report_failure"}[self.path]
                flaky.seen[operation] = flaky.seen.get(operation, 0) + 1
                reply = flaky.api.handle(operation, body)                      # the coordinator DID process it...
                if flaky.seen[operation] <= flaky.drop:
                    self.connection.close()                                    # ...but the answer never arrives
                    return
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def test_a_result_whose_answer_was_lost_is_sent_again_and_acknowledged_not_counted_twice(api, ledger):
    flaky = Flaky(api, drop=2)
    try:
        client = WorkerClient("worker-a", HttpClient(flaky.url, timeout=2.0, retries=3, backoff=0.0))
        work = api.handle("lease", {"worker_id": "worker-a"})["work"]
        from heteroes.worker import Assignment
        from heteroes.manifest import CandidateDescriptor
        assignment = Assignment(CandidateDescriptor.from_dict(work["descriptor"]), work["attempt_number"], work["token"], work["deadline"])

        outcome = client.submit_result(assignment, 0.75)

        assert outcome.name == "ALREADY_COMMITTED"           # the first delivery had committed; the answer to it was lost
        assert flaky.seen["submit_result"] == 3
        assert ledger.get_candidate("exp/g0/c0").result.reward == 0.75
    finally:
        flaky.stop()


def test_a_lease_whose_answer_was_lost_is_not_sent_again(api, ledger):
    flaky = Flaky(api, drop=1)
    try:
        client = WorkerClient("worker-a", HttpClient(flaky.url, timeout=2.0, retries=3, backoff=0.0))

        with pytest.raises(TransportError):
            client.lease()

        assert flaky.seen["lease"] == 1                      # asking again would take a second candidate
        assert ledger.get_candidate("exp/g0/c0").attempts == 1
    finally:
        flaky.stop()


def test_retries_are_bounded(api):
    flaky = Flaky(api, drop=100)
    try:
        client = HttpClient(flaky.url, timeout=2.0, retries=2, backoff=0.0)
        work = api.handle("lease", {"worker_id": "worker-a"})["work"]

        with pytest.raises(TransportError):
            client("report_failure", {"descriptor": work["descriptor"], "attempt_number": 1, "token": work["token"], "kind": "OTHER"})

        assert flaky.seen["report_failure"] == 3             # one try and two retries
    finally:
        flaky.stop()


# ---------------------------------------------------------------------------
# whole generations, with workers in their own threads talking through sockets
# ---------------------------------------------------------------------------

def descriptors(n):
    return [make(i, derive_seed("exp", 0, i)) for i in range(n)]


def reward_of(descriptor):
    return (descriptor.seed % 97) / 96


def run_workers(server, evaluators, stop):
    """Each worker is a thread that keeps taking turns until `stop` is set; returns the log of steps per worker."""
    logs = {name: [] for name in evaluators}

    def loop(name, evaluate):
        worker = Worker(name, HttpClient(server.url, timeout=10.0), evaluate)
        while not stop.is_set():
            step = worker.step()
            logs[name].append(step)
            if step.kind is StepKind.NO_WORK:
                time.sleep(0.005)

    threads = [threading.Thread(target=loop, args=item, daemon=True) for item in evaluators.items()]
    for thread in threads:
        thread.start()
    return threads, logs


def wait_for(condition, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_three_workers_in_threads_finish_a_generation_over_http_and_the_update_is_recorded(tmp_path):
    ledger = Ledger(":memory:", clock=time.time)
    n = 12
    ledger.open_generation(descriptors(n))
    api = WorkerAPI(ledger, "exp", 0, lease_seconds=60.0)
    server = CoordinatorServer(api, job=JOB, models_dir=tmp_path)
    server.start()
    stop = threading.Event()
    seen_oom = set()

    def shared_behaviour(descriptor):
        time.sleep(0.002)                                    # so that the three threads really interleave
        if descriptor.index == 5 and 5 not in seen_oom:      # whoever is given candidate 5 first runs out of memory
            seen_oom.add(5)
            raise CandidateFailed(FailureKind.OUT_OF_MEMORY)
        return reward_of(descriptor)

    try:
        threads, logs = run_workers(server, {"w1": shared_behaviour, "w2": shared_behaviour, "w3": shared_behaviour}, stop)
        assert wait_for(lambda: ledger.get_generation_status("exp", 0).state is GenerationState.COMPLETE), "the generation did not finish"
        stop.set()
        for thread in threads:
            thread.join(timeout=10)
        assert not any(thread.is_alive() for thread in threads)

        results = ledger.get_generation_results("exp", 0)
        assert results.rewards == tuple(reward_of(d) for d in descriptors(n))
        assert server.internal_errors == []
        all_steps = [step for steps in logs.values() for step in steps]
        assert sum(step.kind is StepKind.COMMITTED for step in all_steps) == n
        assert Step(StepKind.FAILURE_REPORTED, "exp/g0/c5", failure=FailureKind.OUT_OF_MEMORY) in all_steps
        assert sum(1 for steps in logs.values() if any(s.kind is StepKind.COMMITTED for s in steps)) >= 2, "premise: the work was shared"
        record = GenerationRecord.from_results("exp", 0, results, alpha=1e-3, eta=1e-9)
        assert ledger.record_update(record) is UpdateOutcome.RECORDED
    finally:
        stop.set()
        server.stop()
        ledger.close()
