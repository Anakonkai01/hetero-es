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
