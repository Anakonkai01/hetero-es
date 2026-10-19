"""
Recipe v3 through the real coordinator, HTTP server and worker loop (ADR-008 sections 5 and 7): workers submit texts, the
coordinator scores them, stores them with the reward, writes version-2 records and applies antithetic pairs merged.
The tiny FP16 model and the seed-dependent texts follow `test_coordinator.py`; the expected child is computed by hand.
"""

import copy
import hashlib

import numpy as np
import pytest

from heteroes.coordinator import ScoringFailed
from heteroes.es.update import apply_coefficients_, apply_es_update_, standardize_rewards
from heteroes.eval.candidate import model_weights_sha256
from heteroes.manifest import derive_seed
from heteroes.model.schema import build_parameter_schema
from heteroes.v3.scoring import ScorerError
from heteroes.worker import StepKind
from test_coordinator import ALPHA, CHUNK, ETA, Env

TEXTS_PER_CANDIDATE = 3


def texts_of(descriptor):
    """What an honest worker would generate: depends on the seed and the sign, so a mix-up changes the reward."""
    return tuple(f"seed {descriptor.seed} sign {descriptor.sign} row {row}" for row in range(TEXTS_PER_CANDIDATE))


def score(generation, descriptor, completions):
    """A scorer of the experiment: per-row scores from the text alone, their mean is the reward."""
    scores = [int(hashlib.sha256(text.encode()).hexdigest()[:4], 16) / 65535 for text in completions]
    return sum(scores) / len(scores)


def v3_env(tmp_path, **options):
    return Env(tmp_path, coefficient_rule="zscore@1", score=score, **options)


def test_without_pairs_v3_gives_the_child_of_todays_update_on_the_same_rewards(tmp_path):
    env = v3_env(tmp_path)
    try:
        env.start_workers(evaluate=texts_of)
        summary = env.coordinator.run_generation(0)
        results = env.ledger.get_generation_results("exp", 0)
        assert results.signs == (1, 1, 1, 1)
        assert list(results.seeds) == [derive_seed("exp", 0, i) for i in range(4)]
        clone = copy.deepcopy(env.initial)
        apply_es_update_(clone, build_parameter_schema(clone), list(results.seeds), results.rewards, ALPHA, CHUNK, ETA)
        assert summary["child_sha256"] == model_weights_sha256(clone, build_parameter_schema(clone))
        stored = env.ledger.get_update("exp", 0).record
        assert stored.coefficient_rule == "zscore@1" and stored.to_dict()["record_version"] == 2
        for index, seed in enumerate(results.seeds):
            descriptor = env.ledger.get_candidate(f"exp/g0/c{index}").descriptor
            sha, texts = env.ledger.get_completions(f"exp/g0/c{index}")
            assert tuple(texts) == texts_of(descriptor) and results.rewards[index] == score(0, descriptor, texts)
    finally:
        env.close()


def test_antithetic_pairs_are_run_signed_and_applied_merged(tmp_path):
    env = v3_env(tmp_path, antithetic=True)
    try:
        env.start_workers(evaluate=texts_of)
        summary = env.coordinator.run_generation(0)
        results = env.ledger.get_generation_results("exp", 0)
        pair_seeds = [derive_seed("exp", 0, k) for k in range(2)]
        assert list(results.seeds) == [pair_seeds[0]] * 2 + [pair_seeds[1]] * 2
        assert results.signs == (1, -1, 1, -1)
        assert len(set(results.rewards)) == 4  # premise: + and - texts differ, so a sign mix-up would show
        z = standardize_rewards(results.rewards, ETA).astype(np.float64)
        merged = ((z[0::2] - z[1::2]) / 2).astype(np.float32)
        clone = copy.deepcopy(env.initial)
        apply_coefficients_(clone, build_parameter_schema(clone), pair_seeds, merged, ALPHA, CHUNK)
        assert summary["child_sha256"] == model_weights_sha256(clone, build_parameter_schema(clone))
        assert env.ledger.get_update("exp", 0).record.signs == (1, -1, 1, -1)
    finally:
        env.close()


def test_an_odd_antithetic_population_is_refused(tmp_path):
    with pytest.raises(Exception, match="even"):
        Env(tmp_path, candidates=3, antithetic=True)


def test_a_scorer_failure_stops_the_generation_and_is_never_a_reward(tmp_path):
    def broken(generation, descriptor, completions):
        raise ScorerError("the scorer of the experiment crashed")

    env = Env(
        tmp_path, coefficient_rule="zscore@1", score=broken, timeout_seconds=10.0
    )  # bounded if the error were missed
    try:
        env.start_workers(names=("w1",), evaluate=texts_of)
        with pytest.raises(ScoringFailed, match="crashed"):
            env.coordinator.run_generation(0)
        assert all(env.ledger.get_candidate(f"exp/g0/c{i}").result is None for i in range(4))
        refused = [step for step in env.logs["w1"] if step.kind is StepKind.REFUSED]
        assert refused and refused[0].code == "scorer_failed"
    finally:
        env.close()


def test_a_scoring_coordinator_refuses_a_reward_and_a_plain_one_refuses_texts(tmp_path):
    # a refused report leaves the lease held, so the generation can only time out: that is the point
    scoring = v3_env(tmp_path / "a", timeout_seconds=1.0)
    plain = Env(tmp_path / "b", timeout_seconds=1.0)
    try:
        scoring.start_workers(names=("w1",), evaluate=lambda descriptor: 0.5)
        plain.start_workers(names=("w2",), evaluate=texts_of)
        for env, name in ((scoring, "w1"), (plain, "w2")):
            with pytest.raises(TimeoutError):
                env.coordinator.run_generation(0)
            assert any(step.kind is StepKind.REFUSED and step.code == "rejected" for step in env.logs[name])
    finally:
        scoring.close()
        plain.close()
