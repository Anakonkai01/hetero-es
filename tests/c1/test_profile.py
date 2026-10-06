"""
`heteroes.profile`: the probe of prompt chunks, the safe chunk, the summary of candidate times and the key of a profile.
No model and no GPU: the evaluation is a fake whose answers depend on the chunk, so the expected result is known by hand.
"""
import contextlib

import pytest

from heteroes.profile import ChunkProbe, key_hash, probe_chunks, profile_key, safe_chunk, summarize_times


class FakeOOM(Exception):
    pass


def is_oom(error):
    return isinstance(error, FakeOOM)


class Env:
    """A fake model: `answers(chunk, condition)` gives the texts. `condition` is the index of the condition being evaluated."""

    def __init__(self, answers, conditions=2, seconds_per_call=1.0):
        self.answers = answers
        self.state = "parent"
        self.log = []
        self.now = 0.0
        self.seconds = seconds_per_call
        self.peaks = 0
        self.conditions = [self.make(number) for number in range(conditions)]

    def make(self, number):
        @contextlib.contextmanager
        def condition():
            assert self.state == "parent"
            self.state = number
            try:
                yield
            finally:
                self.state = "parent"                  # always put back, also after an exception
        return condition

    def evaluate(self, chunk):
        self.log.append((self.state, chunk))
        self.now += self.seconds
        return self.answers(chunk, self.state)

    def clock(self):
        return self.now


def run(env, chunks=(1, 2, 4), **kwargs):
    return probe_chunks(env.conditions, env.evaluate, chunks, is_oom, env.clock, **kwargs)


REFERENCE = [str(i) for i in range(16)]


def test_a_chunk_with_the_same_answers_everywhere_is_identical_and_safe():
    env = Env(lambda chunk, condition: list(REFERENCE))

    probes = run(env)

    assert [(p.chunk, p.ran, p.identical, p.differing) for p in probes] == [(1, True, True, ()), (2, True, True, ()), (4, True, True, ())]
    assert safe_chunk(probes) == 4


def test_one_different_answer_on_one_condition_makes_the_chunk_not_identical_and_says_where():
    def answers(chunk, condition):
        texts = list(REFERENCE)
        if chunk == 4 and condition == 1:
            texts[9] = "changed"                     # only on the perturbed condition, only one question
        return texts

    probes = run(Env(answers))

    four = probes[-1]
    assert (four.ran, four.identical, four.differing) == (True, False, ((1, 9),))
    assert safe_chunk(probes) == 2                   # 2 is fine, 4 is not


def test_a_chunk_that_changes_the_text_is_not_safe_even_if_a_reward_would_be_the_same():
    # the probe compares TEXTS: "41" against "41." would score the same reward, and still the model computed something else
    probes = run(Env(lambda chunk, condition: [t + ("." if chunk == 2 else "") for t in REFERENCE]), chunks=(1, 2))

    assert probes[1].identical is False and safe_chunk(probes) == 1


def test_the_safe_chunk_is_the_largest_that_is_exact_not_the_first_that_fails():
    def answers(chunk, condition):
        return list(REFERENCE) if chunk != 2 else ["x"] + REFERENCE[1:]        # 2 differs, 4 and 8 do not

    probes = run(Env(answers), chunks=(1, 2, 4, 8))

    assert [p.identical for p in probes] == [True, False, True, True]
    assert safe_chunk(probes) == 8


def test_out_of_memory_marks_the_chunk_as_not_run_and_the_model_is_put_back():
    def answers(chunk, condition):
        if chunk >= 4:
            raise FakeOOM("out of memory")
        return list(REFERENCE)

    env = Env(answers)

    probes = run(env, chunks=(1, 2, 4, 8))

    assert [(p.chunk, p.ran, p.identical, p.seconds) for p in probes][2:] == [(4, False, None, None), (8, False, None, None)]
    assert "FakeOOM" in probes[2].error
    assert env.state == "parent"                     # the condition's cleanup ran
    assert safe_chunk(probes) == 2


def test_a_chunk_one_that_runs_out_of_memory_is_a_broken_worker_not_a_probe_result():
    def answers(chunk, condition):
        raise FakeOOM("out of memory")

    with pytest.raises(FakeOOM):
        run(Env(answers), chunks=(1, 2))


def test_an_error_that_is_not_an_oom_is_never_swallowed():
    def answers(chunk, condition):
        if chunk == 2:
            raise ValueError("a bug")
        return list(REFERENCE)

    env = Env(answers)
    with pytest.raises(ValueError, match="a bug"):
        run(env, chunks=(1, 2))
    assert env.state == "parent"


def test_the_reference_chunk_one_must_be_among_the_chunks():
    with pytest.raises(ValueError, match="include 1"):
        run(Env(lambda c, k: REFERENCE), chunks=(2, 4))
    with pytest.raises(ValueError):
        run(Env(lambda c, k: REFERENCE), chunks=())


def test_chunks_are_probed_once_each_in_increasing_order_whatever_the_input_order():
    env = Env(lambda c, k: REFERENCE, conditions=1)

    run(env, chunks=(4, 1, 2, 2))

    assert env.log == [(0, 1), (0, 1), (0, 2), (0, 4)]      # the reference run, then chunk 1, 2, 4 (once)


def test_the_time_is_the_mean_over_the_conditions_of_one_evaluation():
    env = Env(lambda c, k: REFERENCE, conditions=3, seconds_per_call=2.5)

    assert [p.seconds for p in run(env, chunks=(1, 2))] == [2.5, 2.5]


def test_the_peak_memory_is_the_largest_over_the_conditions_and_reset_before_each_measurement():
    env = Env(lambda c, k: REFERENCE, conditions=2)
    resets, peaks = [], iter([100, 300, 200, 50])

    probes = run(env, chunks=(1, 2), reset_peak=lambda: resets.append(1), peak_bytes=lambda: next(peaks))

    assert [p.peak_bytes for p in probes] == [300, 200]
    assert len(resets) == 4


def test_an_unknown_peak_memory_is_none_not_zero():
    probes = run(Env(lambda c, k: REFERENCE), chunks=(1,))

    assert probes[0].peak_bytes is None


def test_safe_chunk_without_any_exact_chunk_is_one_the_reference():
    assert safe_chunk([]) == 1
    assert safe_chunk([ChunkProbe(1, False, None, None, None, "x"), ChunkProbe(2, True, False, 1.0, None)]) == 1


def test_a_probe_is_plain_data_for_the_profile_file():
    assert ChunkProbe(2, True, False, 1.5, 7, None, ((1, 9),)).to_dict() == {
        "chunk": 2, "ran": True, "identical": False, "seconds": 1.5, "peak_bytes": 7, "error": None, "differing": [[1, 9]]}


# ---------------------------------------------------------------------------
# summarize_times, profile_key
# ---------------------------------------------------------------------------

def sample(total, perturb=1.0, rollout=2.0, restore=0.5):
    return {"perturb": perturb, "rollout": rollout, "restore": restore, "total": total}


def test_the_candidate_times_are_summarized_by_the_median_and_the_extremes():
    summary = summarize_times([sample(4.0, perturb=1), sample(10.0, perturb=9), sample(5.0, perturb=3)])

    assert summary["samples"] == 3
    assert (summary["total_median"], summary["total_min"], summary["total_max"]) == (5.0, 4.0, 10.0)      # not the mean 6.33
    assert summary["phases_median"]["perturb"] == 3
    with pytest.raises(ValueError):
        summarize_times([])


ENVIRONMENT = {"gpu_name": "G", "gpu_capability": [7, 5], "gpu_total_memory_bytes": 6, "nvidia_driver": "595", "torch": "2.13",
               "torch_cuda": "13.2", "numpy": "2.5", "transformers": "5.17", "python": "3.14", "hostname": "box", "platform": "linux"}


def key(**changes):
    arguments = dict(environment=ENVIRONMENT, recipe_hash="r", schema_hash="s", workload_hash="w", device="cuda")
    arguments.update(changes)
    return profile_key(**arguments)


def test_the_key_changes_with_every_thing_a_profile_depends_on():
    base = key_hash(key())
    variants = [key(recipe_hash="r2"), key(schema_hash="s2"), key(workload_hash="w2"), key(device="cpu")]
    variants += [key(environment={**ENVIRONMENT, name: other}) for name, other in
                 [("gpu_name", "H"), ("gpu_capability", [8, 6]), ("gpu_total_memory_bytes", 7), ("nvidia_driver", "596"),
                  ("torch", "2.14"), ("torch_cuda", "13.3"), ("numpy", "2.6"), ("transformers", "5.18"), ("python", "3.15")]]

    hashes = [key_hash(variant) for variant in variants]

    assert base not in hashes and len(set(hashes)) == len(hashes)


def test_the_key_does_not_change_with_the_name_of_the_host_or_the_time():
    assert key_hash(key(environment={**ENVIRONMENT, "hostname": "other box", "platform": "other"})) == key_hash(key())
