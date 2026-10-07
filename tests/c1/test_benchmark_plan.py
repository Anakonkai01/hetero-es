"""`scripts/run_benchmark.py: plan`: who works, with which chunk and policy, for each condition (pure function, no process is started)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_benchmark as rb  # noqa: E402

REFERENCE = {"candidate_seconds_at_chunk_1": 4.0, "safe_chunk": 16}
CANDIDATE = {"candidate_seconds_at_chunk_1": 16.0, "safe_chunk": 1}


def prediction(state):
    return {"variants": {"per_worker_chunk": {"decision_b3": {"state": state}}}}


def plan(condition, n=8, state="ELIGIBLE_BUT_NOT_BENEFICIAL"):
    return rb.plan(condition, n, REFERENCE, CANDIDATE, prediction(state))


def test_b0_is_the_fast_worker_alone_with_chunk_one():
    assert plan("B0") == {"workers": {rb.FAST: 1}, "policy": "greedy", "args": []}


def test_b1_and_b3_use_both_workers_with_chunk_one_and_differ_only_in_the_policy():
    b1, b3 = plan("B1"), plan("B3")

    assert b1["workers"] == b3["workers"] == {rb.FAST: 1, rb.SLOW: 1}
    assert (b1["policy"], b1["args"]) == ("wave", ["--wave-size", "2"]) and b3["policy"] == "greedy"


def test_b2_shares_the_candidates_by_the_measured_speed_and_the_quotas_add_up():
    result = plan("B2", n=10)

    assert result["quotas"] == {rb.FAST: 8, rb.SLOW: 2}                       # speeds 1/4 and 1/16: 4 to 1
    assert result["args"] == ["--quota", f"{rb.SLOW}=2", "--quota", f"{rb.FAST}=8"]
    assert sum(result["quotas"].values()) == 10


def test_h0_follows_the_admission_and_uses_each_workers_safe_chunk():
    alone = plan("H0", state="ELIGIBLE_BUT_NOT_BENEFICIAL")
    both = plan("H0", state="ADMITTED")
    limited = plan("H0", state="ADMITTED_LIMITED")
    refused = plan("H0", state="INELIGIBLE")

    assert alone["workers"] == {rb.FAST: 16} and alone["args"] == ["--admit", rb.FAST]
    assert both["workers"] == limited["workers"] == {rb.FAST: 16, rb.SLOW: 1}
    assert refused["workers"] == {rb.FAST: 16}
    assert alone["workers"] != plan("B0")["workers"]                            # H0 alone is not B0: the chunk differs


def test_h0_without_a_prediction_and_an_unknown_condition_are_refused():
    with pytest.raises(ValueError, match="prediction"):
        rb.plan("H0", 8, REFERENCE, CANDIDATE, None)
    with pytest.raises(ValueError):
        rb.plan("B9", 8, REFERENCE, CANDIDATE, None)


# ---- G6: a failed run is set aside, not skipped; a finished one is kept

def test_a_run_directory_is_new_ok_or_failed(tmp_path):
    assert rb.existing_run_state(tmp_path / "n8-B0-r1") == "new"
    run = tmp_path / "n8-B0-r1"
    run.mkdir()
    assert rb.existing_run_state(run) == "failed"                             # a directory without a record: it never finished
    (run / "run.json").write_text('{"outcome": "TimeoutError: x"}')
    assert rb.existing_run_state(run) == "failed"
    (run / "run.json").write_text("not json")
    assert rb.existing_run_state(run) == "failed"
    (run / "run.json").write_text('{"outcome": "ok"}')
    assert rb.existing_run_state(run) == "ok"


def test_a_failed_attempt_is_renamed_never_deleted_and_the_numbers_do_not_collide(tmp_path):
    run = tmp_path / "n8-B0-r1"
    run.mkdir()
    (run / "proof.txt").write_text("evidence")
    first = rb.set_aside(run)
    assert first.name == "n8-B0-r1.failed-attempt1" and (first / "proof.txt").read_text() == "evidence" and not run.exists()
    run.mkdir()
    assert rb.set_aside(run).name == "n8-B0-r1.failed-attempt2"


# ---- G6: several worker processes on the fast GPU

def test_a_condition_may_ask_for_several_processes_on_the_fast_gpu():
    assert rb.parse_condition("B3") == ("B3", 1) and rb.parse_condition("B0x2") == ("B0", 2) and rb.parse_condition("B3x12") == ("B3", 12)
    for bad in ("B", "b0", "B0x", "B0x0", "B0x-1", "B0y2", "BB0", "B0x2x3"):
        with pytest.raises(ValueError):
            rb.parse_condition(bad)
    assert rb.fast_worker_ids(1) == [rb.FAST] and rb.fast_worker_ids(3) == [rb.FAST, f"{rb.FAST}-2", f"{rb.FAST}-3"]


def test_b0x2_is_two_processes_on_the_fast_gpu_and_nothing_else():
    assert plan("B0x2") == {"workers": {rb.FAST: 1, f"{rb.FAST}-2": 1}, "policy": "greedy", "args": []}


def test_b3x2_adds_the_slow_worker_to_the_two_fast_processes():
    result = plan("B3x2")
    assert result["workers"] == {rb.FAST: 1, f"{rb.FAST}-2": 1, rb.SLOW: 1} and result["policy"] == "greedy"


def test_b1x2_waves_are_as_wide_as_the_number_of_workers():
    assert plan("B1x2")["args"] == ["--wave-size", "3"]


def test_b2x2_quotas_split_the_fast_share_between_the_two_processes_and_add_up():
    result = plan("B2x2", n=18)                                               # speeds 1/4, 1/4 and 1/16: shares 8, 8 and 2
    assert result["quotas"] == {rb.FAST: 8, f"{rb.FAST}-2": 8, rb.SLOW: 2} and sum(result["quotas"].values()) == 18


def test_h0_is_for_one_process_only():
    with pytest.raises(ValueError, match="one process"):
        plan("H0x2")


def test_b4_uses_the_tail_policy_and_starts_from_the_profile_speeds():
    result = plan("B4")
    assert result["workers"] == {rb.FAST: 1, rb.SLOW: 1} and result["policy"] == "tail"
    assert result["args"] == ["--speed-prior", f"{rb.SLOW}=16.0", "--speed-prior", f"{rb.FAST}=4.0"]


def test_b4x2_gives_every_fast_process_the_fast_speed():
    result = plan("B4x2")
    assert set(result["workers"]) == {rb.FAST, f"{rb.FAST}-2", rb.SLOW}
    assert result["args"].count("--speed-prior") == 3 and f"{rb.FAST}-2=4.0" in result["args"]


def test_the_speed_of_a_worker_is_taken_at_the_chunk_it_will_use_when_the_profile_timed_it_there():
    profile = {"candidate_seconds_at_chunk_1": 4.0, "candidate_times": {"1": {"total_median": 4.0}, "16": {"total_median": 1.0}}}
    assert rb.seconds_at(profile, 16) == 1.0 and rb.seconds_at(profile, 1) == 4.0
    assert rb.seconds_at(profile, 8) == 4.0                                    # not timed at 8: the chunk-1 time, as the profiles of G4 and G5
    assert rb.seconds_at({"candidate_seconds_at_chunk_1": 7.0}, 16) == 7.0     # an old profile without the table


def test_b4_priors_follow_the_chunk_of_the_run():
    fast = {"candidate_seconds_at_chunk_1": 4.0, "safe_chunk": 16, "candidate_times": {"16": {"total_median": 1.0}}}
    slow = {"candidate_seconds_at_chunk_1": 16.0, "safe_chunk": 16, "candidate_times": {"16": {"total_median": 6.0}}}
    result = rb.plan("B4", 8, fast, slow, None, chunk=16)
    assert result["args"] == ["--speed-prior", f"{rb.SLOW}=6.0", "--speed-prior", f"{rb.FAST}=1.0"]
    assert result["workers"] == {rb.FAST: 16, rb.SLOW: 16}
