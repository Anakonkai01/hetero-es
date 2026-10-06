"""
`CandidateExecutor`: what a worker's GPU does for one candidate, as the `evaluate(descriptor) -> reward` of `Worker`.

    check the job is for this model -> perturb (sigma, chunk size of the recipe) -> evaluate -> restore (verified bit for bit)

The tests use a tiny FP16 model on the CPU and replace `evaluate_model` with a function of the weights it is given, so the
reward tells which weights were evaluated; the real model is checked in the scripts and in the experiment.
Failures are typed (`CandidateFailed`) and never a reward; the model must always come back to the parent weights.
"""
import copy

import pytest
import torch
import torch.nn as nn

import heteroes.executor as executor_module
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import RestoreError
from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.generate import EvalResult
from heteroes.executor import CandidateExecutor
from heteroes.ledger import FailureKind
from heteroes.manifest import CandidateDescriptor, Recipe
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ENGINE_VERSION
from heteroes.worker import CandidateFailed

SIGMA = 1e-3
CHUNK = 16


class HalfToy(nn.Module):
    def __init__(self, seed=0):
        super().__init__()
        torch.manual_seed(seed)
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(4, 4)
        self.half()


def make_recipe(schema, sigma=SIGMA, chunk=CHUNK):
    return Recipe(model_id="toy", model_revision="1" * 40, tokenizer_revision="1" * 40, dtype="torch.float16",
                  schema_hash=schema.hash, engine_version=ENGINE_VERSION, chunk_elements=chunk, noise_fingerprint="2" * 64,
                  sigma=sigma, reward_eta=1e-9, workload_hash="3" * 64, generation_config_sha256="4" * 64)


def descriptor_for(recipe, parent, seed, index=0, generation=0):
    return CandidateDescriptor(recipe_hash=recipe.hash, parent_weights_sha256=parent, experiment_id="exp",
                               generation=generation, index=index, seed=seed)


def reward_from_weights(model, schema):
    """A reward that depends on every bit of the weights: 16 bits of the hash, as a fraction."""
    return int(model_weights_sha256(model, schema)[:4], 16) / 65535


class Fixture:
    def __init__(self, monkeypatch):
        self.model = HalfToy(0)
        self.schema = build_parameter_schema(self.model)
        self.recipe = make_recipe(self.schema)
        self.parent = model_weights_sha256(self.model, self.schema)
        self.seen = []                                                  # the weights hash at each evaluation
        self.clock_value = 0.0
        self.oom_next = False

        def fake_evaluate(model, tokenizer, chunk=1):
            if self.oom_next:
                self.oom_next = False
                raise torch.cuda.OutOfMemoryError("CUDA out of memory")
            self.seen.append(model_weights_sha256(model, self.schema))
            return EvalResult(mean_reward=reward_from_weights(model, self.schema), records=())

        monkeypatch.setattr(executor_module, "evaluate_model", fake_evaluate)

    def tick(self):
        self.clock_value += 1.0
        return self.clock_value

    def executor(self):
        return CandidateExecutor(self.model, None, self.schema, self.recipe, clock=self.tick)

    def descriptor(self, seed=7, **changes):
        base = descriptor_for(self.recipe, self.parent, seed)
        return CandidateDescriptor(**{**base.to_dict(), **changes})

    def expected_perturbed(self, seed, sigma=SIGMA, chunk=CHUNK):
        clone = copy.deepcopy(self.model)
        perturb_model_(clone, build_parameter_schema(clone), seed, sigma, chunk)
        return model_weights_sha256(clone, build_parameter_schema(clone))


@pytest.fixture
def fx(monkeypatch):
    return Fixture(monkeypatch)


def current(fx):
    return model_weights_sha256(fx.model, fx.schema)


# ---------------------------------------------------------------------------
# the normal life of a candidate
# ---------------------------------------------------------------------------

def test_the_candidate_is_evaluated_perturbed_and_the_model_comes_back(fx):
    executor = fx.executor()
    expected = fx.expected_perturbed(7)
    assert expected != fx.parent                                        # premise: the perturbation changes the weights

    reward = executor(fx.descriptor(7))

    assert fx.seen == [expected]                                        # evaluated with the perturbed weights
    assert reward == int(expected[:4], 16) / 65535 and isinstance(reward, float)
    assert current(fx) == fx.parent                                     # restored, bit for bit


def test_the_sigma_and_the_chunk_size_come_from_the_recipe(fx):
    for sigma, chunk in [(2e-3, CHUNK), (SIGMA, 5)]:
        fx.recipe = make_recipe(fx.schema, sigma=sigma, chunk=chunk)
        fx.seen.clear()
        executor = fx.executor()

        executor(fx.descriptor(7))

        assert fx.seen == [fx.expected_perturbed(7, sigma, chunk)]
    assert fx.expected_perturbed(7, 2e-3, CHUNK) != fx.expected_perturbed(7, SIGMA, CHUNK)       # premise: sigma matters
    assert fx.expected_perturbed(7, SIGMA, 5) != fx.expected_perturbed(7, SIGMA, CHUNK)          # and so does the chunk size


def test_the_seed_of_the_descriptor_decides_the_candidate(fx):
    executor = fx.executor()

    first, second = executor(fx.descriptor(7)), executor(fx.descriptor(8))

    assert fx.seen == [fx.expected_perturbed(7), fx.expected_perturbed(8)]
    assert first != second


def test_the_same_candidate_gives_the_same_reward_every_time_and_leaves_nothing_behind(fx):
    executor = fx.executor()

    rewards = [executor(fx.descriptor(7)) for _ in range(3)] + [executor(fx.descriptor(9)), executor(fx.descriptor(7))]

    assert rewards[0] == rewards[1] == rewards[2] == rewards[4]
    assert current(fx) == fx.parent


def test_the_phases_are_timed_in_order(fx):
    executor = fx.executor()

    executor(fx.descriptor(7))

    timing = executor.last_timing
    assert set(timing) == {"perturb", "rollout", "restore", "total"}
    assert timing["perturb"] == timing["rollout"] == timing["restore"] == 1.0 and timing["total"] == 3.0      # the clock ticks once per mark


def test_the_parent_hash_is_computed_once_and_is_the_model_hash(fx):
    executor = fx.executor()

    assert executor.parent_sha256 == fx.parent


# ---------------------------------------------------------------------------
# a job that is not for this model is refused before anything is touched
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("changes", [dict(recipe_hash="9" * 64), dict(parent_weights_sha256="9" * 64)])
def test_a_job_for_another_recipe_or_other_weights_is_refused_and_nothing_runs(fx, changes):
    executor = fx.executor()

    with pytest.raises(CandidateFailed) as caught:
        executor(fx.descriptor(7, **changes))

    assert caught.value.kind is FailureKind.OTHER
    assert ("recipe" in str(caught.value)) == ("recipe_hash" in changes) and ("parent" in str(caught.value)) == ("parent_weights_sha256" in changes)
    assert fx.seen == [] and current(fx) == fx.parent and executor.last_timing is None


# ---------------------------------------------------------------------------
# failures: typed, and the model always comes back
# ---------------------------------------------------------------------------

def test_running_out_of_memory_while_evaluating_is_an_oom_failure_and_the_model_is_restored(fx, monkeypatch):
    def oom(model, tokenizer, chunk=1):
        raise torch.cuda.OutOfMemoryError("CUDA out of memory")

    monkeypatch.setattr(executor_module, "evaluate_model", oom)
    executor = fx.executor()

    with pytest.raises(CandidateFailed) as caught:
        executor(fx.descriptor(7))

    assert caught.value.kind is FailureKind.OUT_OF_MEMORY
    assert current(fx) == fx.parent


def test_running_out_of_memory_while_perturbing_is_an_oom_failure_and_the_model_is_restored(fx, monkeypatch):
    real = executor_module.perturb_model_

    def half_way_then_oom(model, schema, seed, sigma, chunk):
        real(model, schema, seed, sigma, chunk)                         # the weights HAVE changed when it fails
        raise torch.cuda.OutOfMemoryError("CUDA out of memory")

    monkeypatch.setattr(executor_module, "perturb_model_", half_way_then_oom)
    executor = fx.executor()

    with pytest.raises(CandidateFailed) as caught:
        executor(fx.descriptor(7))

    assert caught.value.kind is FailureKind.OUT_OF_MEMORY and current(fx) == fx.parent and fx.seen == []


def test_a_candidate_that_failed_can_be_run_again_and_gives_the_normal_reward(fx):
    executor = fx.executor()
    clean = executor(fx.descriptor(7))

    fx.oom_next = True
    with pytest.raises(CandidateFailed):
        executor(fx.descriptor(7))

    assert executor(fx.descriptor(7)) == clean and current(fx) == fx.parent


def test_a_restore_that_fails_is_a_restore_mismatch_even_though_the_evaluation_was_fine(fx, monkeypatch):
    def broken_restore(model, schema, snapshot):
        raise RestoreError("1 tensor differs")

    monkeypatch.setattr(executor_module, "restore_from_snapshot_", broken_restore)
    executor = fx.executor()

    with pytest.raises(CandidateFailed) as caught:
        executor(fx.descriptor(7))

    assert caught.value.kind is FailureKind.RESTORE_MISMATCH and len(fx.seen) == 1


def test_a_restore_that_fails_after_another_failure_is_still_a_restore_mismatch(fx, monkeypatch):
    def oom(model, tokenizer, chunk=1):
        raise torch.cuda.OutOfMemoryError("CUDA out of memory")

    def broken_restore(model, schema, snapshot):
        raise RestoreError("1 tensor differs")

    monkeypatch.setattr(executor_module, "evaluate_model", oom)
    monkeypatch.setattr(executor_module, "restore_from_snapshot_", broken_restore)
    executor = fx.executor()

    with pytest.raises(CandidateFailed) as caught:
        executor(fx.descriptor(7))

    assert caught.value.kind is FailureKind.RESTORE_MISMATCH               # the weights are in doubt: that matters most


def test_an_unexpected_exception_is_not_swallowed_and_the_model_is_restored_first(fx, monkeypatch):
    def bug(model, tokenizer, chunk=1):
        raise ValueError("a bug in the evaluator")

    monkeypatch.setattr(executor_module, "evaluate_model", bug)
    executor = fx.executor()

    with pytest.raises(ValueError, match="a bug in the evaluator"):
        executor(fx.descriptor(7))

    assert current(fx) == fx.parent


def test_the_timing_of_a_failed_candidate_is_not_reported_as_if_it_had_finished(fx, monkeypatch):
    executor = fx.executor()
    executor(fx.descriptor(7))
    assert executor.last_timing is not None

    def oom(model, tokenizer, chunk=1):
        raise torch.cuda.OutOfMemoryError("x")

    monkeypatch.setattr(executor_module, "evaluate_model", oom)
    with pytest.raises(CandidateFailed):
        executor(fx.descriptor(8))

    assert executor.last_timing is None


# ---------------------------------------------------------------------------
# a new parent (full synchronization replaced the weights)
# ---------------------------------------------------------------------------

def test_after_the_weights_are_replaced_the_executor_works_on_the_new_parent(fx):
    executor = fx.executor()
    old_parent = fx.parent
    with torch.no_grad():                                               # the "synchronization": other weights arrive
        for parameter, other in zip(fx.model.parameters(), HalfToy(5).parameters()):
            parameter.copy_(other)
    new_parent = model_weights_sha256(fx.model, fx.schema)
    assert new_parent != old_parent

    assert executor.reset_parent() == new_parent

    assert executor.parent_sha256 == new_parent
    with pytest.raises(CandidateFailed):                                # a job for the old parent is now refused
        executor(fx.descriptor(7))
    fx.parent = new_parent
    fx.seen.clear()
    executor(fx.descriptor(7))
    assert current(fx) == new_parent                                    # and it is restored to the NEW parent
    assert fx.seen == [fx.expected_perturbed(7)]


def test_resetting_the_parent_takes_the_hash_it_is_given_only_if_it_is_the_truth(fx):
    executor = fx.executor()
    with torch.no_grad():                                               # the weights changed since the executor was made
        for parameter, other in zip(fx.model.parameters(), HalfToy(5).parameters()):
            parameter.copy_(other)
    changed = model_weights_sha256(fx.model, fx.schema)
    assert changed != fx.parent

    with pytest.raises(ValueError, match="hash"):
        executor.reset_parent("0" * 64)

    assert executor.parent_sha256 == fx.parent                          # nothing was taken over
    with pytest.raises(CandidateFailed):                                # and a job for the new weights is still refused
        executor(fx.descriptor(7, parent_weights_sha256=changed))
    assert executor.reset_parent(changed) == changed and executor.parent_sha256 == changed


def test_the_reward_is_a_plain_float_even_if_the_evaluation_gives_a_numpy_number(fx, monkeypatch):
    import numpy as np

    monkeypatch.setattr(executor_module, "evaluate_model", lambda model, tokenizer, chunk=1: EvalResult(np.float32(0.25), ()))

    reward = fx.executor()(fx.descriptor(7))

    assert type(reward) is float and reward == 0.25


# ---------------------------------------------------------------------------
# the number of prompts per generate() call (the "chunk" of MASTER) is the worker's own choice
# ---------------------------------------------------------------------------

def test_the_prompt_chunk_of_the_executor_reaches_the_evaluation(fx, monkeypatch):
    received = []

    def spy(model, tokenizer, chunk=1):
        received.append(chunk)
        return EvalResult(mean_reward=0.5, records=())

    monkeypatch.setattr(executor_module, "evaluate_model", spy)

    CandidateExecutor(fx.model, None, fx.schema, fx.recipe)(fx.descriptor(7))
    CandidateExecutor(fx.model, None, fx.schema, fx.recipe, chunk=8)(fx.descriptor(7))

    assert received == [1, 8]                                           # the default is one prompt at a time


@pytest.mark.parametrize("bad", [0, -1, 1.0, True, "4", None])
def test_a_bad_prompt_chunk_is_refused_at_construction(fx, bad):
    with pytest.raises(ValueError):
        CandidateExecutor(fx.model, None, fx.schema, fx.recipe, chunk=bad)
