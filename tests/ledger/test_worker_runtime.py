"""
`WorkerRuntime`: the life of a worker process, with a real HTTP coordinator and a tiny model on the CPU.

    admit (health, the job's recipe is this worker's recipe) -> loop: look at the job; if its parent weights are not mine,
    download them (hash checked BEFORE the model is touched) and load them; take a turn (`Worker.step`); log what happened

It stops when the coordinator says the experiment is finished, when it is put in quarantine, or when it is told to.
A network error is not a reason to die: the worker waits and asks again.
"""
import copy
import json
import threading
import time

import pytest
import torch
import torch.nn as nn

import heteroes.executor as executor_module
from heteroes.es.perturb import perturb_model_
from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.generate import EvalResult
from heteroes.executor import CandidateExecutor
from heteroes.http_transport import CoordinatorServer, HttpClient, TransportError
from heteroes.ledger import FailureKind, GenerationState, Ledger
from heteroes.manifest import CandidateDescriptor, Recipe, derive_seed
from heteroes.model.schema import build_parameter_schema
from heteroes.model.weights_io import WeightsFileError, publish_weights
from heteroes.noise.contracts import ENGINE_VERSION
from heteroes.worker import CandidateFailed
from heteroes.worker_api import WorkerAPI
from heteroes.worker_runtime import AdmissionError, WorkerRuntime, download_weights

CHUNK = 16
SIGMA = 1e-3


class HalfToy(nn.Module):
    def __init__(self, seed=0):
        super().__init__()
        torch.manual_seed(seed)
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(4, 4)
        self.half()


def make_recipe(schema):
    return Recipe(model_id="toy", model_revision="1" * 40, tokenizer_revision="1" * 40, dtype="torch.float16",
                  schema_hash=schema.hash, engine_version=ENGINE_VERSION, chunk_elements=CHUNK, noise_fingerprint="2" * 64,
                  sigma=SIGMA, reward_eta=1e-9, workload_hash="3" * 64, generation_config_sha256="4" * 64)


def wait_for(condition, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


class Coordinator:
    """Just enough of a coordinator for a worker: a ledger, a server, generations opened by hand."""

    def __init__(self, tmp_path, n=4, parent_model=None, lease_seconds=60.0):
        self.lease_seconds = lease_seconds
        self.model = HalfToy(0) if parent_model is None else parent_model
        self.schema = build_parameter_schema(self.model)
        self.recipe = make_recipe(self.schema)
        self.models_dir = tmp_path / "published"
        self.parent = publish_weights(self.model, self.schema, self.models_dir)
        self.ledger = Ledger(":memory:", clock=time.time)
        self.n = n
        self.server = None
        self.current = None

    def job(self, generation, parent, state="RUNNING"):
        return {"experiment_id": "exp", "generation": generation, "recipe": self.recipe.to_dict(), "recipe_hash": self.recipe.hash,
                "parent_weights_sha256": parent, "state": state}

    def open_generation(self, generation, parent):
        descriptors = [CandidateDescriptor(recipe_hash=self.recipe.hash, parent_weights_sha256=parent, experiment_id="exp",
                                           generation=generation, index=i, seed=derive_seed("exp", generation, i))
                       for i in range(self.n)]
        self.ledger.open_generation(descriptors)
        api = WorkerAPI(self.ledger, "exp", generation, lease_seconds=self.lease_seconds)
        job = self.job(generation, parent)
        if self.server is None:
            self.server = CoordinatorServer(api, job=job, models_dir=self.models_dir)
            self.server.start()
        else:
            self.server.set_generation(api, job)
        self.current = generation

    def wait_complete(self, generation=None):
        generation = self.current if generation is None else generation
        return wait_for(lambda: self.ledger.get_generation_status("exp", generation).state is GenerationState.COMPLETE)

    def finish(self):
        self.server.set_generation(self.server.api, dict(self.server.job, state="FINISHED"))

    def close(self):
        if self.server is not None:
            self.server.stop()
        self.ledger.close()


class WorkerSide:
    def __init__(self, coordinator, monkeypatch, name="worker-a", evaluate=None, model=None, **runtime_args):
        self.model = HalfToy(0) if model is None else model
        self.schema = build_parameter_schema(self.model)
        self.recipe = make_recipe(self.schema)
        self.evaluated = []
        self.events = []
        self.dir = coordinator.models_dir.parent / f"cache-{name}"
        self.dir.mkdir(exist_ok=True)

        def fake_evaluate(model, tokenizer, chunk=1):
            self.evaluated.append(model_weights_sha256(model, self.schema))
            if evaluate is not None:
                evaluate()
            return EvalResult(mean_reward=int(self.evaluated[-1][:4], 16) / 65535, records=())

        monkeypatch.setattr(executor_module, "evaluate_model", fake_evaluate)
        self.executor = CandidateExecutor(self.model, None, self.schema, self.recipe)
        self.client = HttpClient(coordinator.server.url, timeout=5.0, retries=1, backoff=0.0) if coordinator.server else None
        self.coordinator = coordinator
        self.runtime_args = dict(poll_seconds=0.005, **runtime_args)
        self.name = name
        self.stop = threading.Event()
        self.result = None
        self.thread = None

    def runtime(self):
        return WorkerRuntime(self.name, self.client, self.executor, self.dir, log=self.events.append, **self.runtime_args)

    def start(self):
        runtime = self.runtime()

        def run():
            try:
                self.result = runtime.run(self.stop)
            except BaseException as error:        # noqa: BLE001
                self.result = error

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self

    def join(self, seconds=30):
        self.thread.join(timeout=seconds)
        assert not self.thread.is_alive(), "the worker did not stop"
        return self.result

    def kinds(self):
        return [event["event"] for event in self.events]


@pytest.fixture
def coordinator(tmp_path):
    coordinator = Coordinator(tmp_path)
    coordinator.open_generation(0, coordinator.parent)
    yield coordinator
    coordinator.close()


# ---------------------------------------------------------------------------
# admission
# ---------------------------------------------------------------------------

def test_a_worker_with_the_same_recipe_is_admitted_and_gets_the_job(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch)

    job = side.runtime().admit()

    assert job == coordinator.job(0, coordinator.parent)


def test_a_worker_with_another_recipe_is_not_admitted_and_is_told_what_differs(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch)
    side.executor.recipe = Recipe(**{**side.recipe.__dict__, "sigma": 5e-3, "workload_hash": "7" * 64})

    with pytest.raises(AdmissionError) as caught:
        side.runtime().admit()

    assert "sigma" in str(caught.value) and "workload" in str(caught.value) and "chunk" not in str(caught.value)


def test_a_coordinator_that_is_not_there_is_a_transport_error_at_admission(tmp_path, monkeypatch):
    coordinator = Coordinator(tmp_path)
    coordinator.open_generation(0, coordinator.parent)
    side = WorkerSide(coordinator, monkeypatch)
    url = coordinator.server.url
    coordinator.close()
    side.client = HttpClient(url, timeout=1.0, retries=0)

    with pytest.raises(TransportError):
        side.runtime().admit()


def test_a_coordinator_that_has_no_job_yet_is_waited_for(coordinator, monkeypatch):
    coordinator.server.set_generation(coordinator.server.api, None)
    side = WorkerSide(coordinator, monkeypatch)

    assert side.runtime().admit() is None


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------

def test_the_worker_finishes_a_generation_and_stops_when_the_experiment_is_finished(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch).start()

    assert coordinator.wait_complete()
    coordinator.finish()

    assert side.join() == "finished"
    results = coordinator.ledger.get_generation_results("exp", 0)
    assert len(results.rewards) == 4 and len(side.evaluated) == 4
    steps = [e for e in side.events if e["event"] == "step"]
    assert [s["kind"] for s in steps if s["kind"] != "NO_WORK"] == ["COMMITTED"] * 4
    assert side.kinds()[0] == "start" and side.kinds()[-1] == "exit" and side.events[-1]["reason"] == "finished"


def test_a_step_event_says_what_happened_and_how_long_each_part_took(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch).start()
    assert coordinator.wait_complete()
    coordinator.finish()
    side.join()

    step = next(e for e in side.events if e["event"] == "step" and e["kind"] == "COMMITTED")

    assert step["candidate_id"].startswith("exp/g0/c") and step["worker_id"] == "worker-a"
    assert set(step["timing"]) == {"perturb", "rollout", "restore", "total"}
    assert step["step_seconds"] >= step["timing"]["total"] >= 0
    assert step["coordination_seconds"] == pytest.approx(step["step_seconds"] - step["timing"]["total"])
    json.dumps(side.events)                                                  # every event is plain JSON


def test_a_stop_request_stops_the_worker(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch).start()
    assert coordinator.wait_complete()

    side.stop.set()

    assert side.join() == "stopped"


def test_a_worker_put_in_quarantine_stops_with_that_reason(coordinator, monkeypatch):
    def restore_fails():
        raise CandidateFailed(FailureKind.RESTORE_MISMATCH)

    side = WorkerSide(coordinator, monkeypatch, evaluate=restore_fails).start()

    assert side.join() == "quarantined"
    assert [q.worker_id for q in coordinator.ledger.list_quarantined()] == ["worker-a"]


def test_a_worker_whose_recipe_changes_under_it_stops_with_an_error(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch)
    side.start()
    assert coordinator.wait_complete()

    other = dict(coordinator.server.job, recipe_hash="9" * 64)
    coordinator.server.set_generation(coordinator.server.api, other)

    assert isinstance(side.join(), AdmissionError)


def test_the_worker_survives_the_coordinator_going_away_and_coming_back(tmp_path, monkeypatch):
    coordinator = Coordinator(tmp_path, n=6, lease_seconds=0.5)     # a result lost on the way is recovered when its lease runs out
    coordinator.open_generation(0, coordinator.parent)
    side = WorkerSide(coordinator, monkeypatch)
    side.client = HttpClient(coordinator.server.url, timeout=1.0, retries=0)
    side.runtime_args["backoff_seconds"] = 0.01
    port = coordinator.server.port
    side.start()
    try:
        assert wait_for(lambda: coordinator.ledger.get_generation_status("exp", 0).committed >= 1)

        api, job = coordinator.server.api, coordinator.server.job
        coordinator.server.stop()                                               # the coordinator goes away...
        time.sleep(0.3)
        assert side.thread.is_alive()                                            # ...and the worker waits
        coordinator.server = CoordinatorServer(api, job=job, models_dir=coordinator.models_dir, port=port)
        coordinator.server.start()                                               # ...and comes back

        assert coordinator.wait_complete()
        coordinator.finish()
        assert side.join() == "finished"
        assert any(e["event"] == "transport_error" for e in side.events)
    finally:
        side.stop.set()
        coordinator.close()


# ---------------------------------------------------------------------------
# full synchronization: the next generation has other parent weights
# ---------------------------------------------------------------------------

def test_the_worker_downloads_checks_and_loads_the_new_parent_before_it_works_on_it(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch).start()
    assert coordinator.wait_complete()
    first_parent = coordinator.parent
    evaluated_before = len(side.evaluated)

    child_model = HalfToy(5)                                                  # the "updated" model of the coordinator
    child = publish_weights(child_model, build_parameter_schema(child_model), coordinator.models_dir)
    assert child != first_parent
    coordinator.open_generation(1, child)
    assert coordinator.wait_complete(1)
    coordinator.finish()

    assert side.join() == "finished"
    syncs = [e for e in side.events if e["event"] == "sync"]
    assert len(syncs) == 1 and syncs[0]["from_sha256"] == first_parent and syncs[0]["to_sha256"] == child
    assert set(syncs[0]) >= {"transfer_seconds", "load_seconds", "rehash_seconds", "bytes"}
    assert syncs[0]["bytes"] == (coordinator.models_dir / f"{child}.bin").stat().st_size
    assert side.executor.parent_sha256 == child and model_weights_sha256(side.model, side.schema) == child
    expected = set()
    for index in range(4):                                                    # what each candidate of generation 1 must have looked like
        clone = copy.deepcopy(child_model)
        perturb_model_(clone, build_parameter_schema(clone), derive_seed("exp", 1, index), SIGMA, CHUNK)
        expected.add(model_weights_sha256(clone, build_parameter_schema(clone)))
    assert set(side.evaluated[evaluated_before:]) == expected and len(side.evaluated) == evaluated_before + 4
    assert sorted(p.name for p in side.dir.iterdir()) == [f"{child}.bin"]       # the cache keeps only the weights in use
    assert not any(e["event"] == "step" and e["kind"] == "FAILURE_REPORTED" for e in side.events)


def test_a_worker_that_already_has_the_weights_downloads_nothing(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch).start()
    assert coordinator.wait_complete()
    coordinator.open_generation(1, coordinator.parent)                         # same parent again (an update that changed nothing)
    assert coordinator.wait_complete(1)
    coordinator.finish()

    assert side.join() == "finished"
    assert [e for e in side.events if e["event"] == "sync"] == []


def test_two_workers_both_follow_the_new_parent(coordinator, monkeypatch):
    first = WorkerSide(coordinator, monkeypatch, "worker-a").start()
    second = WorkerSide(coordinator, monkeypatch, "worker-b").start()
    assert coordinator.wait_complete()
    child_model = HalfToy(5)
    child = publish_weights(child_model, build_parameter_schema(child_model), coordinator.models_dir)

    coordinator.open_generation(1, child)
    assert coordinator.wait_complete(1)
    coordinator.finish()

    assert first.join() == "finished" and second.join() == "finished"
    assert first.executor.parent_sha256 == second.executor.parent_sha256 == child


# ---------------------------------------------------------------------------
# download_weights
# ---------------------------------------------------------------------------

def test_a_download_is_checked_against_its_name_and_kept_in_the_cache(coordinator, tmp_path):
    client = HttpClient(coordinator.server.url, timeout=5.0)
    cache = tmp_path / "cache"

    path = download_weights(client, coordinator.parent, cache)

    assert path == cache / f"{coordinator.parent}.bin" and path.read_bytes() == (coordinator.models_dir / f"{coordinator.parent}.bin").read_bytes()
    assert [p.name for p in cache.iterdir()] == [f"{coordinator.parent}.bin"]


def test_a_cache_directory_whose_parents_do_not_exist_yet_is_created(coordinator, tmp_path):
    cache = tmp_path / "not" / "there" / "yet" / "cache"
    client = HttpClient(coordinator.server.url, timeout=5.0)

    path = download_weights(client, coordinator.parent, cache)

    assert path == cache / f"{coordinator.parent}.bin" and path.is_file()


def test_a_file_already_in_the_cache_is_not_downloaded_again_if_it_is_intact(coordinator, tmp_path):
    cache = tmp_path / "cache"
    client = HttpClient(coordinator.server.url, timeout=5.0)
    download_weights(client, coordinator.parent, cache)
    coordinator.server.stop()                                                   # nobody to download from now

    assert download_weights(HttpClient(coordinator.server.url, timeout=0.5, retries=0), coordinator.parent, cache).is_file()


def test_a_corrupted_file_in_the_cache_is_replaced(coordinator, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / f"{coordinator.parent}.bin").write_bytes(b"garbage")
    client = HttpClient(coordinator.server.url, timeout=5.0)

    path = download_weights(client, coordinator.parent, cache)

    assert path.read_bytes() == (coordinator.models_dir / f"{coordinator.parent}.bin").read_bytes()


def test_a_download_whose_content_is_not_what_its_name_says_is_refused_and_leaves_nothing(coordinator, tmp_path):
    name = "a" * 64
    (coordinator.models_dir / f"{name}.bin").write_bytes(b"these bytes do not hash to that name")
    cache = tmp_path / "cache"

    with pytest.raises(WeightsFileError, match="hash"):
        download_weights(HttpClient(coordinator.server.url, timeout=5.0), name, cache)

    assert list(cache.iterdir()) == []


def test_downloading_a_model_that_is_not_published_is_a_transport_error(coordinator, tmp_path):
    with pytest.raises(TransportError) as caught:
        download_weights(HttpClient(coordinator.server.url, timeout=5.0), "b" * 64, tmp_path / "cache")

    assert caught.value.status == 404


# ---------------------------------------------------------------------------
# more of the loop
# ---------------------------------------------------------------------------

def test_a_worker_that_starts_before_the_coordinator_has_a_job_waits_for_it(coordinator, monkeypatch):
    api, job = coordinator.server.api, coordinator.server.job
    coordinator.server.set_generation(api, None)
    side = WorkerSide(coordinator, monkeypatch).start()
    time.sleep(0.2)
    assert side.thread.is_alive() and side.evaluated == []

    coordinator.server.set_generation(api, job)

    assert coordinator.wait_complete()
    coordinator.finish()
    assert side.join() == "finished"


def test_a_transfer_whose_hash_is_wrong_is_tried_again_and_then_the_worker_gives_up_without_touching_its_model(coordinator, monkeypatch):
    import heteroes.worker_runtime as runtime_module

    side = WorkerSide(coordinator, monkeypatch)
    child_model = HalfToy(5)
    child = publish_weights(child_model, build_parameter_schema(child_model), coordinator.models_dir)
    job = coordinator.job(1, child)
    real = runtime_module.download_weights
    calls = []

    def bad_then_good(client, sha, directory):
        calls.append(sha)
        if len(calls) == 1:
            raise WeightsFileError("what arrived is not the file: wrong hash")
        return real(client, sha, directory)

    monkeypatch.setattr(runtime_module, "download_weights", bad_then_good)
    runtime = side.runtime()
    runtime.sync(job)
    assert len(calls) == 2 and side.executor.parent_sha256 == child                # the second try worked

    calls.clear()
    other = HalfToy(6)
    other_sha = publish_weights(other, build_parameter_schema(other), coordinator.models_dir)
    before = model_weights_sha256(side.model, side.schema)
    monkeypatch.setattr(runtime_module, "download_weights", lambda *a: (calls.append(1), (_ for _ in ()).throw(WeightsFileError("wrong hash")))[1])

    with pytest.raises(WeightsFileError):
        runtime.sync(coordinator.job(2, other_sha))

    assert len(calls) == 2                                                          # two attempts, no more
    assert model_weights_sha256(side.model, side.schema) == before and side.executor.parent_sha256 == child


def test_only_the_weights_in_use_stay_in_the_cache_after_several_syncs(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch)
    runtime = side.runtime()
    shas = []
    for seed in (5, 6, 7):
        model = HalfToy(seed)
        shas.append(publish_weights(model, build_parameter_schema(model), coordinator.models_dir))
        runtime.sync(coordinator.job(seed, shas[-1]))

    assert sorted(p.name for p in side.dir.iterdir()) == [f"{shas[-1]}.bin"]


def test_a_coordinator_that_does_not_say_it_is_up_is_not_admitted(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch)

    class NotUp:
        def get_json(self, path):
            return {"ok": False} if path == "/v1/health" else {"ok": True, "job": None}

    side.client = NotUp()

    with pytest.raises(TransportError, match="health"):
        side.runtime().admit()


def serve_download(handler_body):
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            handler_body(self)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_a_transfer_that_ends_early_is_caught_by_the_hash_and_leaves_nothing(tmp_path):
    def short(handler):
        handler.send_response(200)
        handler.send_header("Content-Length", "1000")
        handler.end_headers()
        handler.wfile.write(b"only ten b")                                   # then the connection closes quietly

    server, url = serve_download(short)
    try:
        with pytest.raises(WeightsFileError, match="hash"):
            download_weights(HttpClient(url, timeout=2.0, retries=0), "c" * 64, tmp_path / "cache")
        assert list((tmp_path / "cache").iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()


def test_a_connection_that_is_reset_during_a_download_is_a_transport_error_and_leaves_nothing(tmp_path):
    import socket
    import struct

    def reset(handler):
        handler.send_response(200)
        handler.send_header("Content-Length", "1000000")
        handler.end_headers()
        handler.wfile.write(b"x" * 1000)
        handler.wfile.flush()
        handler.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        handler.connection.close()                                           # an RST, not a clean close

    server, url = serve_download(reset)
    try:
        with pytest.raises(TransportError, match="broke off"):
            download_weights(HttpClient(url, timeout=2.0, retries=0), "c" * 64, tmp_path / "cache")
        assert list((tmp_path / "cache").iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()


def test_a_worker_gives_up_when_the_coordinator_stays_away_for_too_long(tmp_path, monkeypatch):
    coordinator = Coordinator(tmp_path)
    coordinator.open_generation(0, coordinator.parent)
    side = WorkerSide(coordinator, monkeypatch, max_unreachable_seconds=0.3, backoff_seconds=0.02)
    side.client = HttpClient(coordinator.server.url, timeout=0.5, retries=0)
    coordinator.close()                                                      # nobody is there any more

    side.start()

    assert side.join(seconds=10) == "unreachable"
    errors = [e for e in side.events if e["event"] == "transport_error"]
    assert len(errors) >= 2 and side.events[-1]["event"] == "exit" and side.events[-1]["reason"] == "unreachable"


def test_a_coordinator_that_comes_back_in_time_resets_the_clock_of_a_worker_that_was_about_to_give_up(tmp_path, monkeypatch):
    coordinator = Coordinator(tmp_path, n=6, lease_seconds=0.5)
    coordinator.open_generation(0, coordinator.parent)
    side = WorkerSide(coordinator, monkeypatch, max_unreachable_seconds=1.5, backoff_seconds=0.02)
    side.client = HttpClient(coordinator.server.url, timeout=0.5, retries=0)
    port, api, job = coordinator.server.port, coordinator.server.api, coordinator.server.job
    side.start()
    try:
        for _ in range(3):                                                    # three outages, together longer than the limit
            assert wait_for(lambda: side.thread.is_alive())
            coordinator.server.stop()
            time.sleep(0.8)
            coordinator.server = CoordinatorServer(api, job=job, models_dir=coordinator.models_dir, port=port)
            coordinator.server.start()
            time.sleep(0.4)                                                   # long enough for the worker to talk to it again

        assert side.thread.is_alive()
        assert coordinator.wait_complete()
        coordinator.finish()
        assert side.join() == "finished"
    finally:
        side.stop.set()
        coordinator.close()


def test_a_worker_that_is_asked_to_stop_does_not_have_to_wait_for_the_limit(tmp_path, monkeypatch):
    coordinator = Coordinator(tmp_path)
    coordinator.open_generation(0, coordinator.parent)
    side = WorkerSide(coordinator, monkeypatch, max_unreachable_seconds=60.0, backoff_seconds=0.02)
    side.client = HttpClient(coordinator.server.url, timeout=0.5, retries=0)
    coordinator.close()
    side.start()
    time.sleep(0.2)

    side.stop.set()

    assert side.join(seconds=5) == "stopped"
