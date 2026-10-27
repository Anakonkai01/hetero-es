"""The run-level audit projection read by the lab supervisor (`heteroes.v3.audit.run_outcomes`).

Each case is a real local Recipe v3 run (coordinator, workers, ledger and audit sidecars), read back read-only the way
the supervisor reads a managed run. Missing or unreadable operational evidence is reported as unknown, never as matched.
"""

import shutil
import sqlite3

import pytest

from heteroes.coordinator import Coordinator, CoordinatorError
from heteroes.product.files import read_json, write_json
from heteroes.v3.audit import run_outcomes
from heteroes.v3.local import run_local
from test_v3_audit import lease, result
from test_v3_local import assets, config_for  # noqa: F401  (fixture)


def outcomes(out, active=False, fallback_rate=0.05):
    with sqlite3.connect(f"file:{out / 'ledger.sqlite'}?mode=ro", uri=True) as db:
        return run_outcomes(db, out, "local", fallback_rate=fallback_rate, active=active)


ZERO = {"selected": 0, "matched": 0, "mismatched": 0, "pending": 0, "timedOut": 0, "skipped": 0, "unknown": 0}


@pytest.fixture(scope="module")
def audited(assets, tmp_path_factory):
    out = tmp_path_factory.mktemp("audited") / "run"
    run_local(config_for(assets), out, workers=2, audit_rate=1.0, timeout_seconds=30)
    return out


def test_a_fully_audited_run_counts_each_candidate_once(audited):
    shown = outcomes(audited)
    assert shown == {
        **ZERO,
        "selected": 8,
        "matched": 8,
        "enabled": True,
        "rate": 1.0,
        "known": True,
        "policy": "historical",
        "drainReasons": {"complete": 2},
        "strictStop": None,
        "restoreFaults": [],
    }


def test_missing_operational_evidence_is_unknown_never_matched(audited, tmp_path):
    old = tmp_path / "old"
    shutil.copytree(audited, old)
    shutil.rmtree(old / "audit-state")
    (old / "audit-config.json").unlink()
    with sqlite3.connect(old / "ledger.sqlite") as db:
        db.execute("DELETE FROM audit WHERE candidate_id LIKE 'local/g1/%'")
    shown = outcomes(old, fallback_rate=1.0)
    # the canonical ledger rows still count; the drain of a recorded generation without its sidecar is unknown
    assert shown["matched"] == 4 and shown["unknown"] == 4 and shown["pending"] == 0
    assert shown["known"] is False and shown["rate"] == 1.0
    assert shown["drainReasons"] == {"unknown": 2}


def test_a_conflicting_drain_sidecar_is_not_trusted(audited, tmp_path):
    copy = tmp_path / "conflict"
    shutil.copytree(audited, copy)
    state = read_json(copy / "audit-state" / "g1.json")
    write_json(copy / "audit-state" / "g1.json", {**state, "auditRate": 0.5})
    shown = outcomes(copy)
    assert shown["known"] is False and shown["drainReasons"] == {"complete": 1, "unknown": 1}
    assert shown["matched"] == 8  # canonical rows are still read


def test_one_worker_cannot_audit_itself(assets, tmp_path):
    out = tmp_path / "alone"
    run_local(config_for(assets), out, workers=1, audit_rate=1.0, timeout_seconds=30)
    shown = outcomes(out)
    assert {k: shown[k] for k in ZERO} == {**ZERO, "selected": 8, "skipped": 8}
    assert shown["drainReasons"] == {"insufficient_workers": 2} and shown["known"] is True


def test_zero_coverage_is_disabled_not_successful(assets, tmp_path):
    out = tmp_path / "zero"
    run_local(config_for(assets, generations=1), out, workers=2, audit_rate=0, timeout_seconds=30)
    shown = outcomes(out)
    assert shown["enabled"] is False and shown["rate"] == 0
    assert {k: shown[k] for k in ZERO} == ZERO


def strict_stopped(assets, out, monkeypatch):
    drain = Coordinator._drain_audits

    def mismatching_drain(self, generation, api, policy):
        api.workers = frozenset(["local-0", "auditor"])
        work = lease(api)["work"]
        assert result(api, work, ["an auditor that disagrees"])["ok"]
        return drain(self, generation, api, policy)

    monkeypatch.setattr(Coordinator, "_drain_audits", mismatching_drain)
    monkeypatch.setattr("heteroes.v3.audit_guard.strict_stop_for", lambda recipe: True)
    with pytest.raises(CoordinatorError):
        run_local(config_for(assets, generations=1), out, workers=1, audit_rate=1, timeout_seconds=30)
    return read_json(out / "audit-stop.json")


@pytest.mark.parametrize("active", [True, False])
def test_a_strict_stop_is_shown_with_both_workers(assets, tmp_path, monkeypatch, active):
    out = tmp_path / "strict"
    receipt = strict_stopped(assets, out, monkeypatch)
    shown = outcomes(out, active=active)
    assert shown["strictStop"] == {
        "candidateId": f"local/g0/c{receipt['descriptor']['index']}",
        "generation": 0,
        "originalWorker": "local-0",
        "auditorWorker": "auditor",
    }
    # the open drain of an active run is pending; once the run has ended nothing will complete it
    left = {"pending": 3} if active else {"unknown": 3}
    assert {k: shown[k] for k in ZERO} == {**ZERO, "selected": 4, "mismatched": 1, **left}
    assert shown["drainReasons"] == {"open": 1} and shown["known"] is True


def test_policy_follows_the_frozen_decoder(audited, tmp_path):
    copy = tmp_path / "policy"
    shutil.copytree(audited, copy)
    recipe = read_json(copy / "recipe.json")
    recipe["evaluation"]["decoder"] = "strict_b22_v1"
    write_json(copy / "recipe.json", recipe)
    assert outcomes(copy)["policy"] == "strict-stop"
    (copy / "recipe.json").unlink()
    assert outcomes(copy)["policy"] is None


def test_the_lab_snapshot_carries_the_outcomes_beside_the_compatible_counts(tmp_path):
    from test_usage_projection import Projection
    from test_v3_product import product_config, run_product
    from tinylm import build_tiny_lm

    assets = tmp_path / "assets"
    build_tiny_lm(assets / "model")
    supervisor = Projection({"stateDirectory": str(tmp_path / "runs"), "workers": []}, "fixture")
    run_id = "a" * 32
    root = supervisor.directory(run_id)
    root.mkdir(parents=True)
    run_product(product_config(assets, root, auditRate=1.0), root)
    write_json(root / "state.json", {"status": "COMPLETED"})
    summary = supervisor.snapshot(run_id)["auditSummary"]
    shown = summary["outcomes"]
    # one worker: every selected candidate was skipped, and the old fields keep their meaning
    assert shown["selected"] == 8 and shown["skipped"] == 8 and shown["matched"] == 0 and shown["known"] is True
    assert shown["policy"] == "historical" and shown["drainReasons"] == {"insufficient_workers": 2}
    assert summary["completed"] == 0 and summary["mismatches"] == 0
    # the last generation's drain left open: pending while the run is active, unknown once it has ended
    (root / "audit-state" / "g1.json").unlink()
    with sqlite3.connect(root / "ledger.sqlite") as db:
        db.execute("DELETE FROM generation_update WHERE generation=1")
    for status, label in (("RUNNING", "pending"), ("FAILED", "unknown")):
        write_json(root / "state.json", {"status": status})
        shown = supervisor.snapshot(run_id)["auditSummary"]["outcomes"]
        assert shown[label] == 4 and shown["skipped"] == 4 and shown["drainReasons"]["open"] == 1
    (root / "audit-config.json").unlink()
    assert supervisor.snapshot(run_id)["auditSummary"]["outcomes"]["known"] is False


def test_a_timed_out_drain_counts_the_rest_as_timed_out(assets, tmp_path, monkeypatch):
    from test_audit_guard_integration import _mismatch_during_drain

    out = tmp_path / "timeout"
    _mismatch_during_drain(monkeypatch, {}, close=True)
    run_local(config_for(assets, generations=1), out, workers=1, audit_rate=1, timeout_seconds=30)
    shown = outcomes(out)
    assert {k: shown[k] for k in ZERO} == {**ZERO, "selected": 4, "mismatched": 1, "timedOut": 3}
    assert shown["drainReasons"] == {"timeout": 1} and shown["strictStop"] is None
