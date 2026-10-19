"""`scripts/run_benchmark.py: plan`: who works, with which chunk and policy, for each condition (pure function, no process is started)."""
import json
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


def write_log(run_dir, worker, events):
    (run_dir / f"{worker}.jsonl").write_text("".join(json.dumps({"event": e}) + "\n" for e in events), encoding="utf-8")


def test_a_worker_that_never_got_ready_is_reported(tmp_path):
    write_log(tmp_path, rb.FAST, ["worker_start", "model_loaded", "executor_ready", "start"])
    # the remote worker's log is not there at all (it did not start: wrong arguments, old code): the run must not count as ok
    assert rb.workers_that_did_not_start(tmp_path, [rb.FAST, rb.SLOW]) == [rb.SLOW]


def test_a_log_without_executor_ready_is_a_worker_that_did_not_start(tmp_path):
    write_log(tmp_path, rb.FAST, ["worker_start", "executor_ready"])
    write_log(tmp_path, rb.SLOW, ["worker_start", "model_loaded"])          # died while it prepared
    assert rb.workers_that_did_not_start(tmp_path, [rb.FAST, rb.SLOW]) == [rb.SLOW]


def test_all_workers_ready_gives_nothing_to_report(tmp_path):
    for worker in (rb.FAST, rb.SLOW):
        write_log(tmp_path, worker, ["worker_start", "executor_ready"])
    assert rb.workers_that_did_not_start(tmp_path, [rb.FAST, rb.SLOW]) == []


def test_a_damaged_line_in_a_log_does_not_hide_the_ready_event(tmp_path):
    (tmp_path / f"{rb.FAST}.jsonl").write_text('{"event": "executor_ready"}\n{"event": "ste', encoding="utf-8")
    assert rb.workers_that_did_not_start(tmp_path, [rb.FAST]) == []


THIRD_PROFILE = {"candidate_seconds_at_chunk_1": 8.0, "safe_chunk": 16}


def three(condition, n=24):
    return rb.plan(condition, n, REFERENCE, CANDIDATE, None, 1, THIRD_PROFILE)


def test_t2_is_the_fast_worker_and_the_third_machine():
    assert three("T2") == {"workers": {rb.FAST: 1, rb.THIRD: 1}, "policy": "greedy", "args": []}


def test_t3_is_the_three_machines_greedy():
    assert three("T3") == {"workers": {rb.FAST: 1, rb.SLOW: 1, rb.THIRD: 1}, "policy": "greedy", "args": []}


def test_q3_gives_each_machine_a_quota_by_its_speed_and_the_quotas_add_up():
    result = three("Q3", 28)

    quotas = result["quotas"]
    assert sum(quotas.values()) == 28 and set(quotas) == {rb.FAST, rb.SLOW, rb.THIRD}
    assert quotas[rb.FAST] > quotas[rb.THIRD] > quotas[rb.SLOW]            # 4 s, 8 s and 16 s per candidate
    assert result["policy"] == "proportional"


def test_the_third_machine_conditions_need_its_profile():
    with pytest.raises(ValueError, match="profile-third"):
        rb.plan("T3", 24, REFERENCE, CANDIDATE, None, 1)


def test_the_third_machine_runs_at_the_chunk_asked():
    assert three("T3")["workers"][rb.THIRD] == 1
    assert rb.plan("T2", 24, REFERENCE, CANDIDATE, None, 64, THIRD_PROFILE)["workers"] == {rb.FAST: 64, rb.THIRD: 64}


def test_u2_is_t2_with_the_tail_policy_and_priors_from_the_two_profiles():
    result = three("U2")
    assert result["workers"] == {rb.FAST: 1, rb.THIRD: 1} and result["policy"] == "tail"
    priors = dict(zip(result["args"][1::2], result["args"][0::2]))
    assert result["args"][0::2] == ["--speed-prior"] * 2
    assert sorted(a.split("=")[0] for a in result["args"][1::2]) == sorted([rb.FAST, rb.THIRD])
    seconds = {a.split("=")[0]: float(a.split("=")[1]) for a in result["args"][1::2]}
    assert seconds[rb.FAST] == 4.0                       # REFERENCE: 4 s per candidate at chunk 1
    assert seconds[rb.THIRD] == rb.seconds_at(THIRD_PROFILE, 1) and seconds[rb.THIRD] > seconds[rb.FAST]


def test_u2_needs_the_profile_of_the_third_machine():
    with pytest.raises(ValueError, match="profile-third"):
        rb.plan("U2", 24, REFERENCE, CANDIDATE, None, 1)
