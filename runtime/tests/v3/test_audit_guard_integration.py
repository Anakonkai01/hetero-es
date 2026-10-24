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
