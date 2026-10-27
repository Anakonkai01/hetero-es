"""Regression cases from the overnight recovered run; reporting must not rewrite its evidence."""

import copy
import json

from labkit import draft, login


def test_completed_run_clears_stale_shutdown_notice_and_counts_audits_after_recovery(setup):
    client, store, _ = setup
    headers = login(client, "admin")
    body = draft(client, headers).json()
    run_id = "44e65d7b2975447fa15fe85f115bad92"
    body.update(
        experimentId=run_id,
        status="COMPLETED",
        recipeVersion=3,
        failureReason="Waiting for confirmed worker shutdown",
        auditSummary={"completed": 720, "selected": 719, "mismatches": 0, "quarantinedWorkers": []},
    )
    snapshot = {
        "state": {"status": "COMPLETED", "failureReason": None},
        "completedGenerationCount": 600,
        "generations": [
            {
                "generationId": f"{run_id}.g{g}",
                "status": "COMPLETED",
                "candidateCount": 24,
                "committedCandidateCount": 24,
            }
            for g in range(600)
        ],
        "candidates": [],
    }
    original = copy.deepcopy(body)
    with store.db() as db:
        db.execute(
            "INSERT INTO experiments VALUES (?,?,?,?)", (run_id, "admin", json.dumps(body), json.dumps(snapshot))
        )
    for shown in (
        client.get(f"/api/v1/experiments/{run_id}", headers=headers).json(),
        next(r for r in client.get("/api/v1/experiments", headers=headers).json() if r["experimentId"] == run_id),
    ):
        assert shown.get("failureReason") is None
        assert shown["auditSummary"]["selected"] == 722
        assert shown["auditSummary"]["incomplete"] == 2
        assert shown["auditSummary"]["completed"] == 720
    with store.db() as db:
        assert json.loads(db.execute("SELECT body FROM experiments WHERE id=?", (run_id,)).fetchone()[0]) == original


def test_real_failure_and_unknown_audit_coverage_are_preserved(setup):
    client, store, _ = setup
    headers = login(client, "admin")
    body = draft(client, headers).json()
    body.update(status="FAILED", recipeVersion=3, failureReason="No space left on device")
    body["auditSummary"] = {"completed": 3, "selected": 2, "mismatches": 0, "quarantinedWorkers": []}
    snapshot = {"state": {"status": "FAILED", "failureReason": body["failureReason"]}, "generations": []}
    with store.db() as db:
        store.save(db, body)
        db.execute("UPDATE experiments SET snapshot=? WHERE id=?", (json.dumps(snapshot), body["experimentId"]))
    shown = store.get(body["experimentId"])
    assert shown["failureReason"] == "No space left on device"
    assert shown["auditSummary"]["selected"] is None
    assert shown["auditSummary"]["selectionComplete"] is False


def test_detailed_audit_outcomes_and_a_strict_stop_reach_the_client_unchanged(setup):
    client, store, _ = setup
    headers = login(client, "admin")
    body = draft(client, headers).json()
    outcomes = {
        "selected": 4,
        "matched": 0,
        "mismatched": 1,
        "pending": 0,
        "timedOut": 0,
        "skipped": 0,
        "unknown": 3,
        "enabled": True,
        "rate": 1.0,
        "known": True,
        "policy": "strict-stop",
        "drainReasons": {"open": 1},
        "strictStop": {"candidateId": "r/g0/c2", "generation": 0, "originalWorker": "a", "auditorWorker": "b"},
        "restoreFaults": [],
    }
    failure = "CoordinatorError: Audit text mismatch requires operator review"
    body.update(status="FAILED", recipeVersion=3, failureReason=failure)
    body["auditSummary"] = {"completed": 1, "mismatches": 1, "quarantinedWorkers": [], "outcomes": outcomes}
    snapshot = {"state": {"status": "FAILED", "failureReason": failure}, "generations": []}
    with store.db() as db:
        store.save(db, body)
        db.execute("UPDATE experiments SET snapshot=? WHERE id=?", (json.dumps(snapshot), body["experimentId"]))
    shown = client.get(f"/api/v1/experiments/{body['experimentId']}", headers=headers).json()
    assert shown["failureReason"] == failure
    assert shown["auditSummary"]["outcomes"] == outcomes
    assert shown["auditSummary"]["mismatches"] == 1 and shown["auditSummary"]["completed"] == 1
