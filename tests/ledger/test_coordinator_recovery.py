"""
A coordinator that dies and is started again must find its place in the ledger and the published weights, and finish the experiment with
exactly the weights an uninterrupted run gives (the update is deterministic and the record is written before the weights change).

Each test kills a coordinator at one particular point (a real second Coordinator object on the same ledger file and weights
directory, with the weights of the INITIAL checkpoint in memory, as a restarted process would have), starts another and compares the
final weights with `apply_es_update_` applied by hand to the rewards, which are a function of the seed.
"""
import copy
import threading
import time

import pytest

import heteroes.coordinator as coordinator_module
from heteroes.coordinator import Coordinator, CoordinatorError
from heteroes.eval.candidate import model_weights_sha256
from heteroes.http_transport import HttpClient
from heteroes.ledger import GenerationState, Ledger
from heteroes.manifest import derive_seed
from heteroes.model.schema import build_parameter_schema
from heteroes.model.weights_io import sha256_of_file
from heteroes.worker import StepKind, Worker
from test_coordinator import ALPHA, CHUNK, ETA, HalfToy, make_recipe, reward_of, wait_for


class World:
    """One experiment on disk (ledger file and weights directory) that can be run by one coordinator after another."""

    def __init__(self, tmp_path, candidates=4, **options):
        self.tmp_path = tmp_path
        self.candidates = candidates
        self.ledger_path = tmp_path / "ledger.sqlite"
        self.models_dir = tmp_path / "published"
        self.options = options
        self.running = []
        self.initial = HalfToy(0)
        self.recipe = make_recipe(build_parameter_schema(self.initial))

    def coordinator(self, **extra):
        model = copy.deepcopy(self.initial)               # a restarted process starts from the checkpoint, not from where it died
        schema = build_parameter_schema(model)
        ledger = Ledger(self.ledger_path, clock=time.time, max_attempts=3)
        events = []
        options = {**dict(lease_seconds=60.0, poll_seconds=0.01), **self.options, **extra}
        coordinator = Coordinator(model, schema, self.recipe, ledger, self.models_dir, experiment_id="exp",
                                  candidates=self.candidates, alpha=ALPHA, log=events.append, **options)
        coordinator.events = events
        coordinator.start()
        self.running.append(coordinator)
        return coordinator

    def workers(self, coordinator, names=("w1", "w2"), evaluate=reward_of):
        stop = threading.Event()
        steps = {name: [] for name in names}

        def loop(name):
            worker = Worker(name, HttpClient(coordinator.url, timeout=10.0), evaluate)
            while not stop.is_set():
                step = worker.step()
                steps[name].append(step)
                if step.kind is StepKind.NO_WORK:
                    time.sleep(0.005)

        threads = [threading.Thread(target=loop, args=(name,), daemon=True) for name in names]
        for thread in threads:
            thread.start()

        def halt():
            stop.set()
            for thread in threads:
                thread.join(timeout=5)
        return halt, steps

    def kill(self, coordinator):
        """What a crash leaves: the HTTP server gone and the ledger file as it is (no orderly shutdown of anything else)."""
        coordinator.stop()
        coordinator.ledger.close()

    def oracle(self, generations, rewards=None):
        from heteroes.es.update import apply_es_update_
        clone = copy.deepcopy(self.initial)
        schema = build_parameter_schema(clone)
        for generation in range(generations):
            seeds = [derive_seed("exp", generation, i) for i in range(self.candidates)]
            apply_es_update_(clone, schema, seeds, [reward_of(type("D", (), {"seed": s})) for s in seeds], ALPHA, CHUNK, ETA)
        return model_weights_sha256(clone, schema)

    def close(self):
        for coordinator in self.running:
            try:
                coordinator.stop()
            except Exception:
                pass
            try:
                coordinator.ledger.close()
            except Exception:
                pass


@pytest.fixture
def world(tmp_path):
    world = World(tmp_path)
    yield world
    world.close()


def final_hash(coordinator):
    return model_weights_sha256(coordinator.model, coordinator.schema)


# ---------------------------------------------------------------------------
# where a restarted coordinator finds itself
# ---------------------------------------------------------------------------

def test_a_fresh_experiment_has_nothing_to_recover(world):
    coordinator = world.coordinator()
    before = final_hash(coordinator)

    assert coordinator.recover() == 0
    assert final_hash(coordinator) == before and coordinator.parent_sha256 == before


def test_after_a_crash_between_two_generations_the_next_one_starts_from_the_published_child(world):
    first = world.coordinator()
    halt, _ = world.workers(first)
    first.run_generation(0)
    halt()
    world.kill(first)

    second = world.coordinator()                                          # a new process: initial weights in memory
    assert final_hash(second) != world.oracle(1)
    assert second.recover() == 1
    assert final_hash(second) == world.oracle(1) == second.parent_sha256
    halt, _ = world.workers(second)
    summary = second.run_generation(1)
    halt()
    assert summary["parent_sha256"] == world.oracle(1)
    assert final_hash(second) == world.oracle(2)


def test_a_crash_between_the_record_and_the_update_is_finished_from_the_stored_record(world, monkeypatch):
    first = world.coordinator()
    halt, _ = world.workers(first)
    real = coordinator_module.apply_coefficients_

    def die(*args, **kwargs):
        raise RuntimeError("power cut")

    monkeypatch.setattr(coordinator_module, "apply_coefficients_", die)
    with pytest.raises(RuntimeError, match="power cut"):
        first.run_generation(0)
    halt()
    monkeypatch.setattr(coordinator_module, "apply_coefficients_", real)
    stored = first.ledger.get_update("exp", 0)
    assert stored is not None and stored.child_weights_sha256 is None       # premise: recorded, not applied
    world.kill(first)

    second = world.coordinator()
    assert second.recover() == 1
    assert final_hash(second) == world.oracle(1)
    again = second.ledger.get_update("exp", 0)
    assert again.child_weights_sha256 == world.oracle(1) and again.record_hash == stored.record_hash
    assert (world.models_dir / f"{world.oracle(1)}.bin").is_file()          # and the child is published for the workers


def test_a_crash_after_the_mark_but_before_the_publication_republishes_the_child(world, monkeypatch):
    first = world.coordinator()
    halt, _ = world.workers(first)
    real = coordinator_module.prepare_publication

    def prepare(*args, **kwargs):
        publication = real(*args, **kwargs)

        def die():
            raise RuntimeError("disk full")                                    # the ledger was told the child; the file never got its name

        publication.commit = die
        return publication

    monkeypatch.setattr(coordinator_module, "prepare_publication", prepare)
    with pytest.raises(RuntimeError, match="disk full"):
        first.run_generation(0)
    halt()
    monkeypatch.setattr(coordinator_module, "prepare_publication", real)
    child = world.oracle(1)
    assert first.ledger.get_update("exp", 0).child_weights_sha256 == child       # premise: marked applied
    assert not (world.models_dir / f"{child}.bin").exists()                      # premise: never published
    assert [p.name for p in world.models_dir.iterdir() if p.name.startswith(".tmp")] == []     # and no temporary file is left behind
    world.kill(first)

    second = world.coordinator()
    assert second.recover() == 1
    assert final_hash(second) == child
    assert sha256_of_file(world.models_dir / f"{child}.bin") == child


def test_a_crash_in_the_middle_of_a_generation_resumes_it_and_only_the_missing_candidates_run(world):
    first = world.coordinator()
    first.ledger.open_generation  # the real thing is done by run_generation; here the coordinator is killed while it waits
    done = threading.Event()
    outcome = []

    def run():
        try:
            outcome.append(first.run_generation(0))
        except BaseException as error:                                        # noqa: BLE001
            outcome.append(error)
        done.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert wait_for(lambda: first.ledger.list_generations("exp"))
    # two candidates are committed by hand, as workers would have, then the coordinator "crashes"
    for index in (0, 1):
        descriptor = first.ledger.list_candidates("exp", 0)[index].descriptor
        held = first.ledger.lease(descriptor.candidate_id, "w-before", 60.0)
        first.ledger.submit_result(descriptor, held.attempt_number, held.token, reward_of(descriptor))
    world.kill(first)
    assert wait_for(done.is_set, 10)

    second = world.coordinator()
    assert second.recover() == 0                                              # generation 0 is not finished: resume it
    halt, steps = world.workers(second)
    summary = second.run_generation(0)
    halt()
    committed = [step for name in steps for step in steps[name] if step.kind is StepKind.COMMITTED]
    assert len(committed) == 2                                                # the two that were missing, not four
    assert summary["child_sha256"] == world.oracle(1)
    assert final_hash(second) == world.oracle(1)


def test_run_after_a_recovery_does_only_the_generations_that_are_left(world):
    first = world.coordinator()
    halt, _ = world.workers(first)
    first.run_generation(0)
    halt()
    world.kill(first)

    second = world.coordinator()
    halt, _ = world.workers(second)
    summaries = second.run(3)
    halt()

    assert [s["generation"] for s in summaries] == [1, 2]
    assert final_hash(second) == world.oracle(3)


def test_a_completed_experiment_run_again_has_nothing_to_do_and_keeps_the_final_weights(world):
    first = world.coordinator()
    halt, _ = world.workers(first)
    first.run(2)
    halt()
    world.kill(first)

    second = world.coordinator()
    assert second.run(2) == []
    assert final_hash(second) == world.oracle(2)


# ---------------------------------------------------------------------------
# what it must refuse
# ---------------------------------------------------------------------------

def test_recovery_refuses_when_the_published_parent_is_gone(world, monkeypatch):
    first = world.coordinator()
    halt, _ = world.workers(first)
    first.run(2)                                  # generation 1 started from child 0, which is not what a restarted process has in memory
    halt()
    world.kill(first)
    for file in world.models_dir.glob("*.bin"):
        file.unlink()

    second = world.coordinator()
    with pytest.raises(CoordinatorError, match="cannot recover"):
        second.recover()


def test_recovery_refuses_a_ledger_of_another_recipe(world):
    first = world.coordinator()
    halt, _ = world.workers(first)
    first.run_generation(0)
    halt()
    world.kill(first)

    import dataclasses
    world.recipe = dataclasses.replace(world.recipe, sigma=world.recipe.sigma * 2)
    second = world.coordinator()
    with pytest.raises(CoordinatorError, match="recipe"):
        second.recover()


def test_recovery_refuses_weights_that_are_not_the_recorded_child(world):
    first = world.coordinator()
    halt, _ = world.workers(first)
    first.run_generation(0)
    halt()
    world.kill(first)
    child = world.oracle(1)
    (world.models_dir / f"{child}.bin").write_bytes(b"not the weights")          # corrupted on disk, but still named after the child

    second = world.coordinator()
    second.recover()                                                          # the bad child is replaced by recomputing it from the parent
    assert final_hash(second) == child
    assert sha256_of_file(world.models_dir / f"{child}.bin") == child


# ---------------------------------------------------------------------------
# no progress is an error, not a silent wait
# ---------------------------------------------------------------------------

def test_a_generation_with_no_progress_for_too_long_is_an_error_and_the_model_is_untouched(world):
    coordinator = world.coordinator(stall_seconds=0.3, timeout_seconds=15)       # the timeout only keeps a broken stall rule from hanging the suite
    before = final_hash(coordinator)
    started = time.time()
    with pytest.raises(CoordinatorError, match="no progress"):
        coordinator.run_generation(0)                                         # nobody works
    assert time.time() - started < 10
    assert final_hash(coordinator) == before


def test_progress_resets_the_stall_timer(world):
    coordinator = world.coordinator(stall_seconds=0.6, timeout_seconds=30)

    def slow(descriptor):
        time.sleep(0.3)                                                       # each candidate takes half the stall time, the total is longer
        return reward_of(descriptor)

    halt, _ = world.workers(coordinator, names=("w1",), evaluate=slow)
    summary = coordinator.run_generation(0)
    halt()
    assert summary["wait_seconds"] > 0.6
    assert final_hash(coordinator) == world.oracle(1)


def test_the_default_stall_time_is_a_multiple_of_the_lease(world):
    coordinator = world.coordinator(lease_seconds=40.0)
    assert coordinator._stall == 200.0
    assert world.coordinator(lease_seconds=2.0)._stall == 60.0                # but never below a minute
    assert world.coordinator(lease_seconds=40.0, stall_seconds=None)._stall is None   # and it can be turned off


# ---------------------------------------------------------------------------
# a failed run is not a finished one
# ---------------------------------------------------------------------------

def test_a_run_that_fails_tells_the_workers_it_was_aborted_not_finished(world):
    coordinator = world.coordinator(stall_seconds=0.2, timeout_seconds=15)
    with pytest.raises(CoordinatorError, match="no progress"):
        coordinator.run(1)                                                    # nobody works: it stalls
    assert HttpClient(coordinator.url).get_json("/v1/job")["job"]["state"] == "ABORTED"


def test_a_run_that_ends_well_tells_the_workers_it_is_finished(world):
    coordinator = world.coordinator()
    halt, _ = world.workers(coordinator)
    coordinator.run(1)
    halt()
    assert HttpClient(coordinator.url).get_json("/v1/job")["job"]["state"] == "FINISHED"


# ---------------------------------------------------------------------------
# the published directory does not grow for ever
# ---------------------------------------------------------------------------

def test_only_the_newest_versions_of_the_weights_stay_in_the_published_directory(world):
    coordinator = world.coordinator(keep_published=3)
    halt, _ = world.workers(coordinator)
    coordinator.run(5)
    halt()
    files = sorted(p.name[:-4] for p in world.models_dir.glob("*.bin"))
    assert len(files) == 3
    assert world.oracle(5) in files and world.oracle(4) in files and world.oracle(3) in files        # the current weights and two ancestors
    assert world.oracle(0) not in files and world.oracle(1) not in files
    assert any(e["event"] == "weights_pruned" for e in coordinator.events)


def test_pruning_can_be_turned_off(world):
    coordinator = world.coordinator(keep_published=None)
    halt, _ = world.workers(coordinator)
    coordinator.run(3)
    halt()
    assert len(list(world.models_dir.glob("*.bin"))) == 4                                           # the initial weights and three children


def test_a_restarted_coordinator_can_still_recover_after_pruning(world):
    first = world.coordinator(keep_published=2)
    halt, _ = world.workers(first)
    first.run(3)
    halt()
    world.kill(first)
    second = world.coordinator(keep_published=2)
    assert second.recover() == 3
    assert final_hash(second) == world.oracle(3)


def test_recovery_refuses_to_continue_when_the_stored_record_gives_another_child_than_the_ledger_marked(world):
    first = world.coordinator()
    halt, _ = world.workers(first)
    first.run_generation(0)
    halt()
    world.kill(first)
    child = world.oracle(1)
    (world.models_dir / f"{child}.bin").unlink()                             # the child file is gone: it must be recomputed ...
    import sqlite3
    db = sqlite3.connect(world.ledger_path)
    db.execute("UPDATE generation_update SET child_weights_sha256 = ?", ("f" * 64,))     # ... and the ledger says another child (a corrupted ledger)
    db.commit()
    db.close()

    second = world.coordinator()
    with pytest.raises(CoordinatorError, match="gives"):
        second.recover()


def test_a_coordinator_off_loopback_needs_a_token_or_an_explicit_opt_out(world):
    with pytest.raises(ValueError, match="token"):
        world.coordinator(host="0.0.0.0")
    open_one = world.coordinator(host="0.0.0.0", allow_unauthenticated=True)
    assert open_one.server.host == "0.0.0.0"
    world.coordinator(host="0.0.0.0", token="x")
