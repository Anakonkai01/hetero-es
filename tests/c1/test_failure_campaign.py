"""The pure and file-reading parts of `scripts/failure_campaign.py` (the scenarios themselves need the two machines)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import failure_campaign as fc  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "ledger"))
from heteroes.ledger import Ledger  # noqa: E402
from ledger_helpers import FakeClock, batch, descriptor_of  # noqa: E402


def test_a_scenario_passes_only_if_it_ended_ok_and_with_the_reference_weights():
    reference = "a" * 64
    good = {"name": "kill-worker", "outcome": "ok", "final_weights_sha256": reference}
    assert fc.verdict(good, reference) == {"scenario": "kill-worker", "ended_ok": True, "same_final_weights_as_reference": True, "passed": True}
    assert fc.verdict({**good, "final_weights_sha256": "b" * 64}, reference)["passed"] is False
    assert fc.verdict({**good, "outcome": "TimeoutError: x"}, reference)["passed"] is False
    assert fc.verdict({**good, "final_weights_sha256": None}, reference)["passed"] is False


def test_open_leases_and_committed_count_read_the_ledger_file_read_only(tmp_path):
    path = tmp_path / "ledger.sqlite"
    with Ledger(path, clock=FakeClock()) as ledger:
        ledger.open_generation(batch(3))
        assert fc.open_leases(path, "worker-a") == 0 and fc.committed_count(path) == 0
        held = ledger.lease("exp/g0/c0", "worker-a", 30.0)
        assert fc.open_leases(path, "worker-a") == 1 and fc.open_leases(path, "worker-b") == 0
        ledger.submit_result(descriptor_of(0), held.attempt_number, held.token, 0.5)
        assert fc.open_leases(path, "worker-a") == 0 and fc.committed_count(path) == 1


def test_reading_a_ledger_that_is_not_there_yet_is_zero_not_an_error(tmp_path):
    assert fc.open_leases(tmp_path / "nothing.sqlite", "w") == 0 and fc.committed_count(tmp_path / "nothing.sqlite") == 0


def test_final_hash_is_the_one_of_the_summary_that_ended_ok(tmp_path):
    (tmp_path / "coordinator").mkdir()
    (tmp_path / "coordinator" / "summary.json").write_text(json.dumps({"outcome": "KeyboardInterrupt: SIGKILL", "final_weights_sha256": "x"}))
    assert fc.final_hash(tmp_path) is None
    (tmp_path / "coordinator" / "summary-resume1.json").write_text(json.dumps({"outcome": "ok", "final_weights_sha256": "f" * 64}))
    assert fc.final_hash(tmp_path) == "f" * 64


def test_events_of_skips_a_line_cut_by_a_kill(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"event": "a"}\n{"event": "b"}\n{"event": "c')           # the process was killed in the middle of a line
    assert [e["event"] for e in fc.events_of(path)] == ["a", "b"]
    assert fc.events_of(tmp_path / "missing.jsonl") == []


def test_wait_until_times_out_with_a_message():
    with pytest.raises(TimeoutError, match="the thing"):
        fc.wait_until(lambda: False, 0.1, "the thing", poll=0.02)
    assert fc.wait_until(lambda: "yes", 1, "x") == "yes"
