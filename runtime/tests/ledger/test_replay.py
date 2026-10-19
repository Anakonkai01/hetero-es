"""
Replay in the worker (C4): catching up by applying the coordinator's update records instead of downloading the weights.
A real HTTP server with a tiny CPU model: the expected child weights are made here by applying the same records with the engine, and every claim is checked
against the hash of the weights, not against what the worker says.
"""
import copy

import pytest

from heteroes.es.update import apply_coefficients_, standardize_rewards
from heteroes.eval.candidate import model_weights_sha256
from heteroes.executor import CandidateExecutor
from heteroes.generation_record import GenerationRecord
from heteroes.http_transport import CoordinatorServer, HttpClient, TransportError, UnauthorizedError
from heteroes.model.schema import build_parameter_schema
from heteroes.model.weights_io import publish_weights
from heteroes.replay import ReplayFailed, ReplayPolicy, fetch_chain
from heteroes.worker_runtime import WorkerRuntime
from test_worker_runtime import CHUNK, HalfToy, make_recipe

ETA = 1e-9


class Chain:
    """A coordinator's history: weights W0 -> W1 -> W2 ... with the record of each step, all published and all served."""

    def __init__(self, tmp_path, steps=2, candidates=4):
        self.model = HalfToy(0)
        self.schema = build_parameter_schema(self.model)
        self.recipe = make_recipe(self.schema)
        self.models_dir = tmp_path / "published"
        self.server = CoordinatorServer(api=None, job=None, models_dir=self.models_dir)
        self.hashes = [publish_weights(self.model, self.schema, self.models_dir)]
        self.records = []
        self.candidates = candidates
        for generation in range(steps):
            rewards = tuple(float(i % 3) for i in range(candidates))
            seeds = tuple(1000 * generation + i for i in range(candidates))
            coefficients = tuple(float(c) for c in standardize_rewards(rewards, ETA))
            record = GenerationRecord(experiment_id="exp", generation=generation, recipe_hash=self.recipe.hash, parent_weights_sha256=self.hashes[-1],
                                      seeds=seeds, rewards=rewards, coefficients=coefficients, alpha=1e-3)
            apply_coefficients_(self.model, self.schema, list(seeds), list(record.coefficients), record.alpha, CHUNK)
            self.records.append(record)
            self.hashes.append(publish_weights(self.model, self.schema, self.models_dir))
            self.serve(generation)
        self.server.start()

    def serve(self, generation, record=None, child=None):
        record = self.records[generation] if record is None else record
        self.server.updates[self.hashes[generation]] = {"record_json": record.to_json(), "record_hash": record.hash,
                                                        "child_weights_sha256": self.hashes[generation + 1] if child is None else child}

    def job(self, generation):
        return {"experiment_id": "exp", "generation": generation, "recipe": self.recipe.to_dict(), "recipe_hash": self.recipe.hash,
                "parent_weights_sha256": self.hashes[generation], "candidates": self.candidates, "state": "RUNNING"}

    def close(self):
        self.server.stop()


class Side:
    def __init__(self, chain, tmp_path, policy, at=0):
        self.model = HalfToy(0)
        self.schema = build_parameter_schema(self.model)
        if at:
            from heteroes.model.weights_io import load_weights_
            load_weights_(self.model, self.schema, chain.models_dir / f"{chain.hashes[at]}.bin", chain.hashes[at])
        self.executor = CandidateExecutor(self.model, None, self.schema, chain.recipe)
        self.events = []
        (tmp_path / "cache").mkdir(exist_ok=True)
        self.runtime = WorkerRuntime("w", HttpClient(chain.server.url, timeout=5.0, retries=0), self.executor, tmp_path / "cache",
                                     log=self.events.append, replay=policy)

    def kinds(self):
        return [event["event"] for event in self.events]


@pytest.fixture
def chain(tmp_path):
    chain = Chain(tmp_path)
    yield chain
    chain.close()


def test_replay_gives_the_coordinators_weights_without_a_download(chain, tmp_path):
    side = Side(chain, tmp_path, ReplayPolicy("always"))
    event = side.runtime.bring_up_to_date(chain.job(1))

    assert model_weights_sha256(side.model, side.schema) == chain.hashes[1] == side.executor.parent_sha256
    assert side.kinds() == ["replay"] and event["steps"] == 1 and event["verified"] is True


def test_replay_of_two_updates(chain, tmp_path):
    side = Side(chain, tmp_path, ReplayPolicy("always"))
    side.runtime.bring_up_to_date(chain.job(2))

    assert model_weights_sha256(side.model, side.schema) == chain.hashes[2] == side.executor.parent_sha256
    assert side.events[0]["steps"] == 2


def test_mode_never_synchronizes(chain, tmp_path):
    side = Side(chain, tmp_path, ReplayPolicy("never"))
    side.runtime.bring_up_to_date(chain.job(1))

    assert side.kinds() == ["sync"] and side.executor.parent_sha256 == chain.hashes[1]


def test_no_policy_is_never(chain, tmp_path):
    side = Side(chain, tmp_path, None)
    side.runtime.bring_up_to_date(chain.job(1))

    assert side.kinds() == ["sync"]


@pytest.mark.parametrize("replay_cost,sync_cost,expected", [(0.1, 10.0, "replay"), (10.0, 0.1, "sync")])
def test_auto_takes_the_faster_way_by_the_profile(chain, tmp_path, replay_cost, sync_cost, expected):
    policy = ReplayPolicy("auto", update_seconds_per_candidate=replay_cost / chain.candidates / 2, update_fixed_seconds=0.0, sync_seconds=sync_cost, verify_seconds=replay_cost / 2)
    side = Side(chain, tmp_path, policy)
    side.runtime.bring_up_to_date(chain.job(1))

    assert expected in side.kinds()
    assert side.executor.parent_sha256 == chain.hashes[1] and model_weights_sha256(side.model, side.schema) == chain.hashes[1]


def test_auto_without_numbers_synchronizes(chain, tmp_path):
    side = Side(chain, tmp_path, ReplayPolicy("auto"))
    side.runtime.bring_up_to_date(chain.job(1))

    assert side.kinds() == ["replay_declined", "sync"]


def test_a_missing_update_falls_back_to_the_full_synchronization(chain, tmp_path):
    del chain.server.updates[chain.hashes[0]]
    side = Side(chain, tmp_path, ReplayPolicy("always"))
    side.runtime.bring_up_to_date(chain.job(1))

    assert side.kinds() == ["replay_failed", "sync"]
    assert model_weights_sha256(side.model, side.schema) == chain.hashes[1] == side.executor.parent_sha256


def test_a_record_that_does_not_give_the_coordinators_child_is_caught_by_the_hash_and_the_worker_synchronizes(chain, tmp_path):
    other = GenerationRecord(experiment_id="exp", generation=0, recipe_hash=chain.recipe.hash, parent_weights_sha256=chain.hashes[0], seeds=(5, 6, 7, 8),
                             rewards=(0.0, 1.0, 0.0, 1.0), coefficients=tuple(float(c) for c in standardize_rewards((0.0, 1.0, 0.0, 1.0), ETA)), alpha=1e-3)
    chain.serve(0, record=other)
    side = Side(chain, tmp_path, ReplayPolicy("always"))
    side.runtime.bring_up_to_date(chain.job(1))

    assert side.kinds() == ["replay_failed", "sync"]
    assert model_weights_sha256(side.model, side.schema) == chain.hashes[1] == side.executor.parent_sha256


def test_verify_every_two_trusts_the_first_catch_up_and_checks_the_second(chain, tmp_path):
    side = Side(chain, tmp_path, ReplayPolicy("always", verify_every=2))
    first = side.runtime.bring_up_to_date(chain.job(1))
    second = side.runtime.bring_up_to_date(chain.job(2))

    assert (first["verified"], second["verified"]) == (False, True)
    assert model_weights_sha256(side.model, side.schema) == chain.hashes[2] == side.executor.parent_sha256


def test_a_trusted_replay_that_drifted_is_caught_at_the_next_check(chain, tmp_path):
    other = GenerationRecord(experiment_id="exp", generation=0, recipe_hash=chain.recipe.hash, parent_weights_sha256=chain.hashes[0], seeds=(5, 6, 7, 8),
                             rewards=(0.0, 1.0, 0.0, 1.0), coefficients=tuple(float(c) for c in standardize_rewards((0.0, 1.0, 0.0, 1.0), ETA)), alpha=1e-3)
    chain.serve(0, record=other)
    side = Side(chain, tmp_path, ReplayPolicy("always", verify_every=2))
    first = side.runtime.bring_up_to_date(chain.job(1))                # trusted: the drift is not seen here
    assert first["verified"] is False and side.executor.parent_sha256 == chain.hashes[1]
    assert model_weights_sha256(side.model, side.schema) != chain.hashes[1]

    side.runtime.bring_up_to_date(chain.job(2))                        # checked: the hash differs, the worker synchronizes

    assert side.kinds()[-2:] == ["replay_failed", "sync"]
    assert model_weights_sha256(side.model, side.schema) == chain.hashes[2] == side.executor.parent_sha256


def test_a_network_error_while_fetching_the_records_falls_back_to_the_synchronization(chain, tmp_path, monkeypatch):
    side = Side(chain, tmp_path, ReplayPolicy("always"))

    def broken(parent):
        raise TransportError("the cable was pulled")

    monkeypatch.setattr(side.runtime.client, "get_update", broken)
    side.runtime.bring_up_to_date(chain.job(1))

    assert side.kinds() == ["replay_failed", "sync"] and side.executor.parent_sha256 == chain.hashes[1]


def test_a_wrong_token_is_not_hidden_by_the_fallback(chain, tmp_path, monkeypatch):
    side = Side(chain, tmp_path, ReplayPolicy("always"))

    def refused(parent):
        raise UnauthorizedError("no")

    monkeypatch.setattr(side.runtime.client, "get_update", refused)
    with pytest.raises(UnauthorizedError):
        side.runtime.bring_up_to_date(chain.job(1))


# ---- the pieces ------------------------------------------------------------------------------------------------------------------

def test_fetch_chain_returns_the_records_in_order(chain):
    found = fetch_chain(HttpClient(chain.server.url, retries=0), chain.hashes[0], chain.hashes[2], chain.recipe.hash)
    assert [record.hash for record, _ in found] == [r.hash for r in chain.records]
    assert [child for _, child in found] == chain.hashes[1:]


def test_fetch_chain_refuses_a_record_of_another_parent_recipe_or_hash(chain):
    client = HttpClient(chain.server.url, retries=0)
    update = chain.server.updates[chain.hashes[0]]
    with pytest.raises(ReplayFailed, match="another recipe"):
        fetch_chain(client, chain.hashes[0], chain.hashes[1], "9" * 64)
    chain.server.updates[chain.hashes[0]] = dict(update, record_hash="0" * 64)
    with pytest.raises(ReplayFailed, match="hash"):
        fetch_chain(client, chain.hashes[0], chain.hashes[1], chain.recipe.hash)
    chain.server.updates[chain.hashes[0]] = chain.server.updates[chain.hashes[1]]            # the record of the next step served for this parent
    with pytest.raises(ReplayFailed, match="record served for"):
        fetch_chain(client, chain.hashes[0], chain.hashes[1], chain.recipe.hash)


def test_fetch_chain_refuses_a_loop_and_a_chain_that_is_too_long(chain):
    client = HttpClient(chain.server.url, retries=0)
    chain.serve(1, child=chain.hashes[0])                                                        # the second update claims to lead back to the start
    with pytest.raises(ReplayFailed, match="loops"):
        fetch_chain(client, chain.hashes[0], "f" * 64, chain.recipe.hash)
    chain.serve(1)
    with pytest.raises(ReplayFailed, match="longer than 1"):
        fetch_chain(client, chain.hashes[0], chain.hashes[2], chain.recipe.hash, max_steps=1)


def test_policy_decisions_and_validation():
    assert ReplayPolicy("never").decide(1, 24) == (False, "mode never")
    assert ReplayPolicy("always").decide(5, 24)[0] is True
    slow = ReplayPolicy("auto", update_seconds_per_candidate=0.5, update_fixed_seconds=0.0, sync_seconds=9.8, verify_seconds=3.6)
    assert slow.decide(1, 24)[0] is False                      # 12 + 3.6 s against 9.8 s: the measured case of the 1660S at N = 24
    assert slow.decide(1, 8)[0] is True                        # 4 + 3.6 s against 9.8 s
    with pytest.raises(ValueError):
        ReplayPolicy("sometimes")
    with pytest.raises(ValueError):
        ReplayPolicy("always", verify_every=0)


def test_policy_from_a_profile():
    profile = {"update": {"seconds_per_candidate_median": 0.07, "fixed_seconds": -0.2, "hash_seconds": 3.0}, "sync": {"total_seconds": 21.9}}
    policy = ReplayPolicy.from_profile(profile)
    assert (policy.update_seconds_per_candidate, policy.update_fixed_seconds, policy.verify_seconds, policy.sync_seconds) == (0.07, 0.0, 3.0, 21.9)
    assert ReplayPolicy.from_profile({"update": None, "sync": None}).decide(1, 24)[0] is False


def test_a_long_chain_is_replayed_when_the_policy_allows_it_and_synchronized_when_it_does_not(tmp_path):
    chain = Chain(tmp_path, steps=4)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    try:
        refused = Side(chain, tmp_path / "a", ReplayPolicy("always", max_chain=3))
        refused.runtime.bring_up_to_date(chain.job(4))
        assert refused.kinds() == ["replay_failed", "sync"] and refused.executor.parent_sha256 == chain.hashes[4]

        allowed = Side(chain, tmp_path / "b", ReplayPolicy("always", max_chain=4))
        allowed.runtime.bring_up_to_date(chain.job(4))
        assert allowed.kinds() == ["replay"] and allowed.events[0]["steps"] == 4
        assert model_weights_sha256(allowed.model, allowed.schema) == chain.hashes[4] == allowed.executor.parent_sha256
    finally:
        chain.close()


def test_max_chain_is_validated_and_comes_from_the_profile_call():
    with pytest.raises(ValueError):
        ReplayPolicy("always", max_chain=0)
    assert ReplayPolicy.from_profile({"update": None, "sync": None}, max_chain=50).max_chain == 50
