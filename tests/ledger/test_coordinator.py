"""
`Coordinator`: the process that owns the experiment. For each generation it

    opens the generation in the ledger (parent = its own weights) and tells the HTTP server -> waits until every candidate is committed
    -> writes the update record (BEFORE the weights are touched) -> applies the update to its own model -> marks it applied
    -> publishes the child weights under their hash, so that the workers can synchronize

The tests use a tiny FP16 model on the CPU, real HTTP and workers in their own threads; their reward is a function of the seed, so
the right update is known: it is `apply_es_update_` applied by hand, on a copy, to those rewards.
"""
import copy
import json
import threading
import time

import pytest
import torch
import torch.nn as nn

import heteroes.coordinator as coordinator_module
from heteroes.coordinator import Coordinator, CoordinatorError
from heteroes.dispatch import StaticWave
from heteroes.es.update import apply_es_update_
from heteroes.eval.candidate import model_weights_sha256
from heteroes.http_transport import HttpClient
from heteroes.ledger import FailureKind, GenerationState, Ledger, LedgerError
from heteroes.manifest import Recipe
from heteroes.model.schema import build_parameter_schema
from heteroes.model.weights_io import sha256_of_file
from heteroes.noise.contracts import ENGINE_VERSION
from heteroes.worker import CandidateFailed, StepKind, Worker, WorkerClient

CHUNK = 16
SIGMA = 1e-3
ALPHA = 0.05
ETA = 1e-9


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
                  sigma=SIGMA, reward_eta=ETA, workload_hash="3" * 64, generation_config_sha256="4" * 64)


def reward_of(descriptor):
    return (descriptor.seed % 97) / 96


def wait_for(condition, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


class Env:
    def __init__(self, tmp_path, candidates=4, max_attempts=3, **options):
        self.model = HalfToy(0)
        self.initial = copy.deepcopy(self.model)
        self.schema = build_parameter_schema(self.model)
        self.recipe = make_recipe(self.schema)
        self.ledger = Ledger(":memory:", clock=time.time, max_attempts=max_attempts)
        self.events = []
        self.models_dir = tmp_path / "published"
        self.coordinator = Coordinator(
            self.model, self.schema, self.recipe, self.ledger, self.models_dir, experiment_id="exp", candidates=candidates,
            alpha=ALPHA, lease_seconds=options.pop("lease_seconds", 60.0), poll_seconds=0.01, log=self.events.append, **options)
        self.coordinator.start()
        self.stop = threading.Event()
        self.threads = []
        self.logs = {}

    def start_workers(self, names=("w1", "w2", "w3"), evaluate=None):
        for name in names:
            self.logs[name] = []
            thread = threading.Thread(target=self._loop, args=(name, evaluate or reward_of), daemon=True)
            thread.start()
            self.threads.append(thread)

    def _loop(self, name, evaluate):
        worker = Worker(name, HttpClient(self.coordinator.url, timeout=10.0), evaluate)
        while not self.stop.is_set():
            step = worker.step()
            self.logs[name].append(step)
            if step.kind is StepKind.NO_WORK:
                time.sleep(0.005)

    def job(self):
        return HttpClient(self.coordinator.url).get_json("/v1/job")["job"]

    def oracle_child(self, rewards_by_generation):
        """The model after the updates, computed by hand with apply_es_update_ on a copy (independent of the coordinator)."""
        from heteroes.manifest import derive_seed

        clone = copy.deepcopy(self.initial)
        schema = build_parameter_schema(clone)
        for generation, rewards in enumerate(rewards_by_generation):
            seeds = [derive_seed("exp", generation, i) for i in range(len(rewards))]
            apply_es_update_(clone, schema, seeds, rewards, ALPHA, CHUNK, ETA)
        return model_weights_sha256(clone, schema)

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=5)
        self.coordinator.stop()
        self.ledger.close()


@pytest.fixture
def env(tmp_path):
    env = Env(tmp_path)
    yield env
    env.close()


# ---------------------------------------------------------------------------
# one generation
# ---------------------------------------------------------------------------

def test_a_generation_is_run_recorded_applied_and_published(env):
    parent = model_weights_sha256(env.model, env.schema)
    env.start_workers()

    summary = env.coordinator.run_generation(0)

    assert env.ledger.get_generation_status("exp", 0).state is GenerationState.COMPLETE
    rewards = list(env.ledger.get_generation_results("exp", 0).rewards)
    assert summary["rewards"] == rewards and summary["mean_reward"] == pytest.approx(sum(rewards) / 4)
    child = env.oracle_child([rewards])
    assert child != parent                                                    # premise: the update changed the weights
    assert summary["parent_sha256"] == parent and summary["child_sha256"] == child
    assert model_weights_sha256(env.model, env.schema) == child
    assert env.coordinator.parent_sha256 == child
    stored = env.ledger.get_update("exp", 0)
    assert stored.record_hash == summary["record_hash"] and stored.child_weights_sha256 == child and stored.applied_at is not None
    assert (env.models_dir / f"{child}.bin").is_file() and sha256_of_file(env.models_dir / f"{child}.bin") == child
    assert (env.models_dir / f"{parent}.bin").is_file()                      # the parent is published too: a worker with other weights can sync


def test_the_summary_is_plain_json_with_the_timings_of_each_part(env):
    env.start_workers()

    summary = env.coordinator.run_generation(0)

    json.dumps(summary)
    assert {"generation", "parent_sha256", "child_sha256", "record_hash", "rewards", "mean_reward", "coefficients", "noop",
            "applied_l2", "changed", "wait_seconds", "record_seconds", "update_seconds", "publish_seconds", "total_seconds"} <= set(summary)
    assert summary["total_seconds"] >= summary["wait_seconds"] >= 0 and summary["update_seconds"] >= 0
    assert summary["noop"] is False and summary["changed"] > 0


def test_the_job_tells_the_workers_what_this_generation_is(env):
    env.start_workers()
    env.coordinator.run_generation(0)

    job = env.job()

    assert job["experiment_id"] == "exp" and job["generation"] == 0 and job["state"] == "RUNNING"
    assert job["recipe"] == env.recipe.to_dict() and job["recipe_hash"] == env.recipe.hash
    assert job["candidates"] == 4 and job["policy"] == "Greedy"
    parent = env.ledger.list_candidates("exp", 0)[0].descriptor.parent_weights_sha256
    assert job["parent_weights_sha256"] == parent != model_weights_sha256(env.model, env.schema)     # the parent, not the child


def test_before_a_generation_is_open_there_is_no_job_and_no_work(env):
    client = HttpClient(env.coordinator.url)

    assert client.get_json("/v1/job") == {"ok": True, "job": None}
    assert client("lease", {"worker_id": "w1"}) == {"ok": True, "generation_state": "OPEN", "work": None}
    reply = client("submit_result", {"descriptor": {}, "attempt_number": 1, "token": "x", "reward": 0.5})
    assert reply["ok"] is False and "no generation" in reply["error"]["message"]


def test_the_candidates_carry_the_recipe_the_parent_and_a_seed_of_their_own(env):
    env.start_workers()
    env.coordinator.run_generation(0)

    descriptors = [r.descriptor for r in env.ledger.list_candidates("exp", 0)]

    assert [d.index for d in descriptors] == [0, 1, 2, 3]
    assert {d.recipe_hash for d in descriptors} == {env.recipe.hash}
    assert len({d.seed for d in descriptors}) == 4 and len({d.parent_weights_sha256 for d in descriptors}) == 1


# ---------------------------------------------------------------------------
# the order of things: the record is written before the weights change
# ---------------------------------------------------------------------------

def test_the_update_is_recorded_before_the_weights_are_touched(env, monkeypatch):
    real = coordinator_module.apply_coefficients_
    seen = []

    def inspect_then_apply(model, schema, seeds, coefficients, alpha, chunk_elements):
        stored = env.ledger.get_update("exp", 0)
        seen.append((stored is not None, stored.applied_at if stored else "no record", model_weights_sha256(model, schema)))
        return real(model, schema, seeds, coefficients, alpha, chunk_elements)

    monkeypatch.setattr(coordinator_module, "apply_coefficients_", inspect_then_apply)
    parent = model_weights_sha256(env.model, env.schema)
    env.start_workers()

    env.coordinator.run_generation(0)

    assert seen == [(True, None, parent)]                                     # recorded, not yet applied, weights still the parent's


def test_a_crash_while_applying_leaves_the_record_and_no_child(env, monkeypatch):
    def crash(*args, **kwargs):
        raise RuntimeError("the process died while writing the weights")

    monkeypatch.setattr(coordinator_module, "apply_coefficients_", crash)
    env.start_workers()

    with pytest.raises(RuntimeError, match="died"):
        env.coordinator.run_generation(0)

    stored = env.ledger.get_update("exp", 0)
    assert stored is not None and stored.child_weights_sha256 is None and stored.applied_at is None
    assert list(env.models_dir.glob("*.bin")) == [env.models_dir / f"{env.coordinator.parent_sha256}.bin"]    # nothing was published


# ---------------------------------------------------------------------------
# several generations
# ---------------------------------------------------------------------------

def test_the_next_generation_starts_from_the_child_and_the_updates_accumulate(env):
    env.start_workers()

    first = env.coordinator.run_generation(0)
    second = env.coordinator.run_generation(1)

    assert {r.descriptor.parent_weights_sha256 for r in env.ledger.list_candidates("exp", 1)} == {first["child_sha256"]}
    assert second["parent_sha256"] == first["child_sha256"] != second["child_sha256"]
    rewards = [list(env.ledger.get_generation_results("exp", g).rewards) for g in (0, 1)]
    assert second["child_sha256"] == env.oracle_child(rewards) == model_weights_sha256(env.model, env.schema)
    assert first["rewards"] != second["rewards"]                              # other seeds, other candidates


def test_run_does_every_generation_and_then_tells_the_workers_the_experiment_is_over(env):
    env.start_workers()

    summaries = env.coordinator.run(3)

    assert [s["generation"] for s in summaries] == [0, 1, 2]
    assert [s["parent_sha256"] for s in summaries[1:]] == [s["child_sha256"] for s in summaries[:-1]]
    assert env.job()["state"] == "FINISHED" and env.job()["generation"] == 2


# ---------------------------------------------------------------------------
# when things go wrong
# ---------------------------------------------------------------------------

def test_a_generation_that_can_not_finish_is_an_error_after_the_grace_and_the_model_is_untouched(tmp_path):
    env = Env(tmp_path, max_attempts=1, failed_grace_seconds=0.2)
    parent = model_weights_sha256(env.model, env.schema)

    def always_oom_on_zero(descriptor):
        if descriptor.index == 0:
            raise CandidateFailed(FailureKind.OUT_OF_MEMORY)
        return reward_of(descriptor)

    try:
        env.start_workers(("w1", "w2"), evaluate=always_oom_on_zero)

        with pytest.raises(CoordinatorError, match="exp/g0/c0"):
            env.coordinator.run_generation(0)

        assert model_weights_sha256(env.model, env.schema) == parent
        assert env.ledger.get_update("exp", 0) is None
    finally:
        env.close()


def test_a_late_result_inside_the_grace_period_completes_a_generation_that_looked_failed(tmp_path):
    env = Env(tmp_path, max_attempts=1, lease_seconds=0.3, failed_grace_seconds=10.0)
    try:
        result = {}
        thread = threading.Thread(target=lambda: result.update(env.coordinator.run_generation(0)))
        thread.start()
        assert wait_for(lambda: env.job() is not None)
        slow = WorkerClient("slow", HttpClient(env.coordinator.url, timeout=10.0))
        held = slow.lease()                                                   # candidate 0 is leased... and not answered yet
        assert held.assignment.candidate_id == "exp/g0/c0"
        env.start_workers(("w1", "w2"))

        assert wait_for(lambda: env.ledger.get_generation_status("exp", 0).state is GenerationState.FAILED)
        time.sleep(0.5)                                                       # long enough for a coordinator that gives up at once
        assert thread.is_alive()                                              # the coordinator is waiting, not giving up
        slow.submit_result(held.assignment, reward_of(held.assignment.descriptor))
        thread.join(timeout=20)

        assert not thread.is_alive() and result["rewards"][0] == reward_of(held.assignment.descriptor)
        assert env.ledger.get_generation_status("exp", 0).state is GenerationState.COMPLETE
    finally:
        env.close()


def test_a_generation_in_which_every_reward_is_equal_changes_nothing_and_says_so(env):
    env.start_workers(evaluate=lambda descriptor: 0.5)
    parent = model_weights_sha256(env.model, env.schema)

    summary = env.coordinator.run_generation(0)

    assert summary["noop"] is True and summary["changed"] == 0 and summary["coefficients"] == [0.0] * 4
    assert summary["child_sha256"] == parent == model_weights_sha256(env.model, env.schema)
    stored = env.ledger.get_update("exp", 0)
    assert stored.child_weights_sha256 == parent and stored.record.noop


def test_waiting_for_workers_that_never_come_is_a_timeout_and_the_model_is_untouched(tmp_path):
    env = Env(tmp_path, timeout_seconds=0.3)
    parent = model_weights_sha256(env.model, env.schema)
    try:
        with pytest.raises(TimeoutError):
            env.coordinator.run_generation(0)

        assert model_weights_sha256(env.model, env.schema) == parent and env.ledger.get_update("exp", 0) is None
    finally:
        env.close()


def test_a_generation_cannot_be_run_twice(env):
    env.start_workers()
    env.coordinator.run_generation(0)

    with pytest.raises(LedgerError, match="already"):
        env.coordinator.run_generation(0)


# ---------------------------------------------------------------------------
# options
# ---------------------------------------------------------------------------

def test_a_static_wave_policy_can_be_chosen_and_the_job_says_so(tmp_path):
    env = Env(tmp_path, policy_factory=lambda: StaticWave(2))
    try:
        env.start_workers(("w1", "w2"))

        summary = env.coordinator.run_generation(0)

        assert env.job()["policy"] == "StaticWave"
        assert summary["child_sha256"] == env.oracle_child([summary["rewards"]])
    finally:
        env.close()


def test_every_event_is_plain_json_and_the_phases_come_in_order(env):
    env.start_workers()
    env.coordinator.run_generation(0)

    json.dumps(env.events)
    kinds = [e["event"] for e in env.events]
    assert kinds == ["generation_open", "generation_complete", "update_recorded", "update_applied", "weights_published", "generation_done"]
    assert env.events[0]["generation"] == 0 and env.events[-1]["child_sha256"] == env.coordinator.parent_sha256


def test_the_token_is_passed_to_the_server(tmp_path):
    env = Env(tmp_path, token="s3cret")
    try:
        assert HttpClient(env.coordinator.url, token="s3cret").get_json("/v1/health")["ok"] is True
        from heteroes.http_transport import UnauthorizedError
        with pytest.raises(UnauthorizedError):                                    # G6: a refusal of the token is an error, not a JSON reply to ignore
            HttpClient(env.coordinator.url).get_json("/v1/health")
    finally:
        env.close()
