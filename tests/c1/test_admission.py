"""
`heteroes.admission`: the hard capability gate, the prediction of the time of a generation and the decision to admit.
The predictions are computed by hand in the comments (small numbers), not by calling the code under test.
"""
import pytest

from heteroes.admission import (
    AdmissionState,
    Reason,
    WorkerModel,
    capability_gate,
    decide,
    predict_candidates_seconds,
    predict_generation_seconds,
)

B3, B2 = "B3_GREEDY_DYNAMIC", "B2_STATIC_PROPORTIONAL"
KEY = {"device": "cuda", "gpu_total_memory_bytes": 1000, "recipe_hash": "r"}


def profile(**changes):
    base = {"key": dict(KEY), "peak_bytes_candidate": 500,
            "checks": {"noise_selftest": True, "restore_exact": True, "chunk1_reproduces_reference": True}}
    base.update(changes)
    return base


# ---------------------------------------------------------------------------
# the hard gate
# ---------------------------------------------------------------------------

def test_a_good_profile_passes_the_gate():
    assert capability_gate(profile(), KEY) == []


@pytest.mark.parametrize("changes,reason", [
    ({"key": {**KEY, "device": "cpu"}}, Reason.NOT_A_GPU),
    ({"key": {**KEY, "recipe_hash": "other"}}, Reason.PROFILE_KEY_MISMATCH),
    ({"checks": {"noise_selftest": False, "restore_exact": True, "chunk1_reproduces_reference": True}}, Reason.NOISE_SELFTEST_FAILED),
    ({"checks": {"noise_selftest": True, "restore_exact": False, "chunk1_reproduces_reference": True}}, Reason.RESTORE_FAILED),
    ({"checks": {"noise_selftest": True, "restore_exact": True, "chunk1_reproduces_reference": False}}, Reason.NUMERICS_FAILED),
    ({"peak_bytes_candidate": 950}, Reason.MEMORY_MARGIN),
])
def test_each_failure_has_its_own_reason_code(changes, reason):
    expected_key = KEY if "key" not in changes or changes["key"]["device"] != "cpu" else changes["key"]
    expected_key = {**KEY, "recipe_hash": "r"} if reason is Reason.PROFILE_KEY_MISMATCH else expected_key
    if reason is Reason.PROFILE_KEY_MISMATCH:
        assert capability_gate(profile(**changes), KEY) == [Reason.PROFILE_KEY_MISMATCH]
    else:
        assert reason in capability_gate(profile(**changes), expected_key)


def test_the_memory_margin_is_exactly_the_fraction_of_the_gpu():
    assert capability_gate(profile(peak_bytes_candidate=900), KEY) == []                      # 100 free = 10 %: allowed
    assert capability_gate(profile(peak_bytes_candidate=901), KEY) == [Reason.MEMORY_MARGIN]
    assert capability_gate(profile(peak_bytes_candidate=901), KEY, min_free_fraction=0.05) == []


def test_several_failures_are_all_reported():
    reasons = capability_gate(profile(peak_bytes_candidate=999, checks={"noise_selftest": False, "restore_exact": False,
                                                                       "chunk1_reproduces_reference": False}), KEY)

    assert set(reasons) == {Reason.MEMORY_MARGIN, Reason.NOISE_SELFTEST_FAILED, Reason.RESTORE_FAILED, Reason.NUMERICS_FAILED}


# ---------------------------------------------------------------------------
# prediction
# ---------------------------------------------------------------------------

def test_one_worker_takes_n_times_its_candidate_time():
    assert predict_candidates_seconds(B3, [WorkerModel("a", 4.0)], 8) == {"seconds": 32.0, "jobs": {"a": 8}}


def test_greedy_two_workers_by_hand():
    # a: 4.5 s per candidate, ready at 0. b: 17 s per candidate, ready after a 17 s sync. N = 8.
    # c1 a->4.5  c2 a->9  c3 a->13.5  (b is not ready before 17)  c4 a(13.5)->18  c5: a free at 18, b at 17 -> b->34
    # c6 a(18)->22.5  c7 a->27  c8 a->31.5     the generation ends when b's candidate does: 34
    result = predict_candidates_seconds(B3, [WorkerModel("a", 4.5), WorkerModel("b", 17.0, sync_seconds=17.0)], 8)

    assert result == {"seconds": 34.0, "jobs": {"a": 7, "b": 1}}


def test_greedy_has_the_tail_that_a_slow_worker_adds():
    # the slow worker takes the LAST candidate and the others wait for it: two workers can be slower than one
    alone = predict_candidates_seconds(B3, [WorkerModel("a", 4.0)], 3)["seconds"]
    with_slow = predict_candidates_seconds(B3, [WorkerModel("a", 4.0), WorkerModel("b", 30.0)], 3)["seconds"]
    # a->4, then a(4) vs b(0): b is free at 0 so it takes c2 -> 30; a takes c1 (4), c3 (8): ends 30
    assert alone == 12.0 and with_slow == 30.0


def test_proportional_two_workers_by_hand():
    # speeds 1/4 and 1/16 candidates/s -> ratio 4:1; N = 10 -> exact shares 8 and 2 -> quotas 8 and 2.
    # a: 8 * 4 = 32. b: sync 5 + 2 * 16 = 37. The generation ends at 37.
    result = predict_candidates_seconds(B2, [WorkerModel("a", 4.0), WorkerModel("b", 16.0, sync_seconds=5.0)], 10)

    assert result == {"seconds": 37.0, "jobs": {"a": 8, "b": 2}}


def test_proportional_ignores_a_worker_with_no_quota():
    result = predict_candidates_seconds(B2, [WorkerModel("a", 1.0), WorkerModel("b", 1000.0, sync_seconds=500.0)], 2)

    assert result["jobs"] == {"a": 2, "b": 0} and result["seconds"] == 2.0        # b's sync does not hold the generation


def test_the_generation_adds_the_update_and_the_publication():
    result = predict_generation_seconds(B3, [WorkerModel("a", 4.0)], 8, update_per_candidate=5.75, publish_seconds=0.5)

    assert result["candidates_seconds"] == 32.0 and result["update_seconds"] == 46.0
    assert result["total_seconds"] == 32.0 + 46.0 + 0.5
    assert result["workers"] == ["a"] and result["jobs"] == {"a": 8}


@pytest.mark.parametrize("workers", [[], [WorkerModel("a", 0.0)], [WorkerModel("a", -1.0)], [WorkerModel("a", 1.0, sync_seconds=-1.0)]])
def test_bad_workers_are_refused(workers):
    with pytest.raises(ValueError):
        predict_candidates_seconds(B3, workers, 4)


def test_an_unknown_policy_has_no_prediction():
    with pytest.raises(ValueError):
        predict_candidates_seconds("B9", [WorkerModel("a", 1.0)], 4)


# ---------------------------------------------------------------------------
# the decision
# ---------------------------------------------------------------------------

FAST = WorkerModel("fast", 4.5)
SLOW = WorkerModel("slow", 17.0, sync_seconds=17.0)


def decision(candidate, members=(FAST,), gate=(), policy=B3, candidates=8, update=5.75, publish=0.7, **kwargs):
    return decide(candidate, list(members), list(gate), policy, candidates, update, publish, **kwargs)


def test_the_hard_gate_decides_before_any_benefit_and_nothing_is_predicted():
    result = decision(SLOW, gate=[Reason.NUMERICS_FAILED])

    assert result.state is AdmissionState.INELIGIBLE and result.reasons == (Reason.NUMERICS_FAILED,)
    assert result.without is None and result.with_worker is None and result.predicted_delta_seconds is None


def test_a_slow_worker_with_a_big_sync_cost_is_eligible_but_not_beneficial():
    # without: 8 * 4.5 + 46 + 0.7 = 82.7.  with: 34 + 46 + 0.7 = 80.7.  gain 2.0 s, below 5 % of 82.7 = 4.135 s
    result = decision(SLOW)

    assert result.state is AdmissionState.ELIGIBLE_BUT_NOT_BENEFICIAL and result.reasons == (Reason.NOT_BENEFICIAL,)
    assert result.without["total_seconds"] == pytest.approx(82.7) and result.with_worker["total_seconds"] == pytest.approx(80.7)
    assert result.predicted_delta_seconds == pytest.approx(2.0) and result.delta_threshold == pytest.approx(4.135)


def test_a_worker_that_clearly_helps_is_admitted():
    helper = WorkerModel("helper", 5.0)                      # almost as fast as `fast`, no sync cost
    # without 82.7. with: c1 fast->4.5 c2 helper->5 c3 fast->9 c4 helper->10 c5 fast->13.5 c6 helper->15 c7 fast->18
    # c8: helper is free at 15, fast at 18 -> helper->20.  The candidates end at 20: 20 + 46.7 = 66.7
    result = decision(helper)

    assert result.state is AdmissionState.ADMITTED and result.reasons == (Reason.OK,)
    assert result.predicted_delta_seconds == pytest.approx(82.7 - 66.7)


def test_a_helper_with_a_smaller_chunk_is_admitted_limited():
    result = decision(WorkerModel("helper", 5.0), limited=True)

    assert result.state is AdmissionState.ADMITTED_LIMITED and result.reasons == (Reason.CHUNK_LIMITED,)


def test_the_threshold_is_strict_a_gain_equal_to_delta_is_not_enough():
    base = decision(SLOW)
    exactly = base.predicted_delta_seconds / base.without["total_seconds"]            # delta_fraction that makes gain == threshold

    assert decision(SLOW, delta_fraction=exactly).state is AdmissionState.ELIGIBLE_BUT_NOT_BENEFICIAL
    assert decision(SLOW, delta_fraction=exactly * 0.99).state is AdmissionState.ADMITTED


def test_a_worker_that_makes_the_generation_longer_is_never_admitted_whatever_delta():
    slower = WorkerModel("tail", 60.0)                       # takes a candidate at 0 and the generation waits 60 s for it

    result = decision(slower, delta_fraction=0.0)

    assert result.predicted_delta_seconds < 0 and result.state is AdmissionState.ELIGIBLE_BUT_NOT_BENEFICIAL


def test_the_decision_is_plain_data_for_the_prediction_file():
    data = decision(SLOW).to_dict()

    assert data["worker_id"] == "slow" and data["state"] == "ELIGIBLE_BUT_NOT_BENEFICIAL" and data["reasons"] == ["NOT_BENEFICIAL"]
    assert data["prediction_with"]["jobs"] == {"fast": 7, "slow": 1}


# ---------------------------------------------------------------------------
# from a profile to the numbers of the prediction
# ---------------------------------------------------------------------------

def test_a_worker_model_takes_the_median_at_the_asked_chunk_and_the_sync_only_if_remote():
    from heteroes.admission import worker_model_from_profile
    data = {"worker_id": "w", "candidate_times": {"1": {"total_median": 4.5}, "16": {"total_median": 3.9}},
            "sync": {"total_seconds": 21.0}}

    assert worker_model_from_profile(data, 1, remote=False) == WorkerModel("w", 4.5, 0.0)
    assert worker_model_from_profile(data, 16, remote=True) == WorkerModel("w", 3.9, 21.0)


def test_a_chunk_that_was_not_timed_or_a_missing_sync_is_an_error_not_a_guess():
    from heteroes.admission import worker_model_from_profile
    data = {"worker_id": "w", "candidate_times": {"1": {"total_median": 4.5}, "8": {"failed": "OUT_OF_MEMORY"}}, "sync": None}

    for chunk in (2, 8):
        with pytest.raises(ValueError, match="not timed"):
            worker_model_from_profile(data, chunk, remote=False)
    with pytest.raises(ValueError, match="synchronization"):
        worker_model_from_profile(data, 1, remote=True)
