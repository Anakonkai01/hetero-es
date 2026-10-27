"""A fault after the last cooperative check still blocks the real coordinator's write-ahead admission."""

import sqlite3

import pytest

from heteroes.coordinator import Coordinator, CoordinatorError
from heteroes.v3.audit_guard import AuditRunGuard
from heteroes.v3.local import run_local
from test_v3_audit import lease, result
from test_v3_local import assets, config_for


@pytest.mark.parametrize("fault", ["text", "restore"])
def test_real_coordinator_rechecks_run_guard_at_update_admission(assets, tmp_path, monkeypatch, fault):
    captured = {}
    init, check = Coordinator.__init__, Coordinator._check_cancel

    def fixture_init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        captured["coordinator"] = self
        # Internal fixture only: the actual managed identity remains historical, never promoted by this test.
        assert self._audit_guard.stop_on_mismatch is False
        self._audit_guard = AuditRunGuard(
            self.ledger,
            self.experiment_id,
            fault_path=self._audit_faults,
            stop_path=self._audit_faults.with_name("audit-stop.json"),
            stop_on_mismatch=True,
        )

    def drain(self, generation, api, policy):
        assert api.guard is self._audit_guard
        api.workers = frozenset(["local-0", "auditor"])
        captured["work"] = lease(api)["work"]
        assert captured["work"] is not None
        api.close_drain("timeout")

    def record(event):
        if event.get("event") == "generation_complete":
            captured["armed"] = True

    def check_then_fault(self):
        check(self)
        if captured.pop("armed", False):
            api, work = self._api, captured["work"]
            if fault == "text":
                assert result(api, work, ["mismatch at last boundary"])["ok"]
            else:
                request = {k: work[k] for k in ("descriptor", "attempt_number", "token", "audit_id")}
                reply = api.handle(
                    "report_failure", {**request, "kind": "RESTORE_MISMATCH"}, authenticated_worker_id="auditor"
                )
                assert reply["error"]["code"] == "worker_quarantined"
            # Return after the prior check: only the serialized admission may now catch the fault.

    monkeypatch.setattr(Coordinator, "__init__", fixture_init)
    monkeypatch.setattr(Coordinator, "_drain_audits", drain)
    monkeypatch.setattr(Coordinator, "_check_cancel", check_then_fault)
    out = tmp_path / "run"
    with pytest.raises(CoordinatorError, match="mismatch|restore"):
        run_local(config_for(assets, generations=1), out, workers=1, audit_rate=1, log=record, timeout_seconds=30)
    with sqlite3.connect(out / "ledger.sqlite") as db:
        assert db.execute("SELECT count(*) FROM result").fetchone()[0] == 4
        assert db.execute("SELECT count(*) FROM generation_update").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 0


# ---- D9: the strict decoder stops the run at its first audit text mismatch -----------------------------------------


@pytest.mark.parametrize(
    "changes, strict",
    [
        ({}, False),
        ({"decoder": "hf_generate"}, False),
        ({"decoder": "hf_fp32_cpu_guard_v1"}, False),
        ({"decoder": "strict_b22_v1", "evalDtype": "float16"}, True),
    ],
)
def test_only_the_strict_decoder_identity_stops_at_the_first_mismatch(assets, tmp_path, changes, strict):
    from heteroes.v3.audit_guard import strict_stop_for
    from heteroes.v3.local import prepare

    run = prepare(config_for(assets, **changes), tmp_path / "documents")["run"]
    assert run.evaluation["decoder"] == changes.get("decoder", "hf_generate")
    assert strict_stop_for(run) is strict
    assert strict_stop_for(object()) is False  # a Recipe v1 run has no Recipe v3 evaluation section


def _mismatch_during_drain(monkeypatch, captured, close=False):
    """One extra worker re-executes a candidate and returns other text; the real drain then decides what happens.

    `close` ends the drain as timed out at once (the other selected candidates would otherwise wait for the timeout)."""
    drain = Coordinator._drain_audits

    def mismatching_drain(self, generation, api, policy):
        captured["guard"] = self._audit_guard
        if generation == 0:
            api.workers = frozenset(["local-0", "auditor"])
            work = lease(api)["work"]
            assert work is not None
            assert result(api, work, ["an auditor that disagrees"])["ok"]
            if close:
                api.close_drain("timeout")
        return drain(self, generation, api, policy)

    monkeypatch.setattr(Coordinator, "_drain_audits", mismatching_drain)


def test_a_strict_run_stops_before_the_update_and_keeps_both_texts(assets, tmp_path, monkeypatch):
    import json

    captured = {}
    _mismatch_during_drain(monkeypatch, captured)
    # The strict decoder itself needs an NVIDIA GPU; the decision under test is the coordinator's, so only it is strict.
    monkeypatch.setattr("heteroes.v3.audit_guard.strict_stop_for", lambda recipe: True)
    out = tmp_path / "strict"
    with pytest.raises(CoordinatorError, match="Audit text mismatch requires operator review"):
        run_local(config_for(assets, generations=1), out, workers=1, audit_rate=1, timeout_seconds=30)
    assert captured["guard"].stop_on_mismatch is True
    receipt = json.loads((out / "audit-stop.json").read_text())
    assert receipt["auditor"]["completions"] == ["an auditor that disagrees"]
    assert receipt["original"]["worker_id"] == "local-0" and receipt["original"]["completions"]
    with sqlite3.connect(out / "ledger.sqlite") as db:
        assert db.execute("SELECT count(*) FROM generation_update").fetchone()[0] == 0
        assert db.execute("SELECT matched FROM audit").fetchall() == [(0,)]
        assert db.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 0  # no device decision is made


def test_a_historical_run_records_the_mismatch_and_continues(assets, tmp_path, monkeypatch):
    captured = {}
    _mismatch_during_drain(monkeypatch, captured, close=True)
    out = tmp_path / "historical"
    summaries = run_local(config_for(assets, generations=1), out, workers=1, audit_rate=1, timeout_seconds=30)
    assert captured["guard"].stop_on_mismatch is False
    assert not (out / "audit-stop.json").exists()
    assert summaries[0]["audits"]["mismatched"] == 1 and summaries[0]["audits"]["drain_reason"] == "timeout"
    with sqlite3.connect(out / "ledger.sqlite") as db:
        assert db.execute("SELECT count(*) FROM generation_update").fetchone()[0] == 1
