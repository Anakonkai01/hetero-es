"""The compact, time-ordered view of a run used by the Live, Timeline and Replay screens."""

import json
from pathlib import Path

from backend.timeline import build_timeline

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "run-fifo.json").read_text())


def attempt(candidate, worker, started, completed=None, status="SUCCEEDED", n=1):
    return {
        "experimentId": "r",
        "generationId": "r.g0",
        "candidateId": candidate,
        "attemptId": f"{candidate}.a{n}",
        "workerId": worker,
        "status": status,
        "startedAt": started,
        "completedAt": completed,
        "errorType": None if status != "FAILED" else "WorkerLost",
    }


def candidate(cid, generation, worker=None, status="COMMITTED", reward=None, attempt_id=None):
    return {
        "experimentId": "r",
        "generationId": f"r.g{generation}",
        "candidateId": cid,
        "seed": "7",
        "status": status,
        "reward": reward,
        "workerId": worker,
        "attemptId": attempt_id,
    }


def synthetic():
    t0 = "2026-10-10T08:00:00+00:00"
    return {
        "experimentId": "r",
        "name": "synthetic",
        "status": "RUNNING",
        "createdAt": t0,
        "maxGenerations": 2,
        "candidatesPerGeneration": 3,
    }, {
        "state": {
            "status": "RUNNING",
            "startedAt": 1791619200.0,
            "workerStates": {"a": {"alive": True}, "b": {"alive": True}},
        },
        "generations": [
            {
                "generationId": "r.g0",
                "status": "RUNNING",
                "candidateCount": 3,
                "committedCandidateCount": 1,
                "startedAt": "2026-10-10T08:00:05+00:00",
            }
        ],
        "candidates": [
            candidate("r.g0.c0", 0, "a", "COMMITTED", 0.5, "r.g0.c0.a2"),
            candidate("r.g0.c1", 0, "b", "RUNNING"),
            candidate("r.g0.c2", 0, None, "PENDING"),
        ],
        "attempts": [
            attempt("r.g0.c0", "a", "2026-10-10T08:00:06+00:00", "2026-10-10T08:00:07+00:00", "FAILED", 1),
            attempt("r.g0.c0", "b", "2026-10-10T08:00:08+00:00", "2026-10-10T08:00:10+00:00", "SUCCEEDED", 2),
            attempt("r.g0.c1", "a", "2026-10-10T08:00:09+00:00", None, "RUNNING", 1),
        ],
        "events": [
            {"event": "generation_open", "t": 1791619205.0, "generation": 0, "candidates": 3},
            {"event": "replay", "t": 1791619209.5, "worker_id": "b"},
            {"event": "step", "t": 1791619206.0, "worker_id": "a", "kind": "NO_WORK"},
        ],
        "artifacts": [],
    }


def test_a_real_finished_run_becomes_ordered_jobs_generations_and_workers():
    timeline = build_timeline(FIXTURE["body"], FIXTURE["snapshot"])
    assert (
        timeline["experiment"]["id"] == FIXTURE["body"]["experimentId"]
        and timeline["experiment"]["status"] == "COMPLETED"
    )
    assert timeline["experiment"]["startedMs"] < timeline["experiment"]["completedMs"]
    jobs = timeline["jobs"]
    assert (
        len(jobs) == 2 and {j["workerId"] for j in jobs} == {"5070ti"} and all(j["status"] == "SUCCEEDED" for j in jobs)
    )
    assert [j["startMs"] for j in jobs] == sorted(j["startMs"] for j in jobs)
    assert all(j["endMs"] > j["startMs"] and j["reward"] == 0.25 and j["generation"] == 0 for j in jobs)
    [generation] = timeline["generations"]
    assert generation["openMs"] < generation["evaluatedMs"] < generation["doneMs"]
    assert generation["candidateCount"] == 2 and generation["committedCount"] == 2 and generation["rewardMean"] == 0.25
    assert set(generation["seconds"]) >= {"update", "publish", "total"}
    ids = {w["id"]: w for w in timeline["workers"]}
    assert set(ids) == {"5070ti", "3060"} and ids["3060"]["started"] is False and ids["5070ti"]["started"] is True


def test_a_candidate_retried_on_another_worker_is_two_jobs_and_the_reward_belongs_to_the_one_that_committed():
    body, snapshot = synthetic()
    jobs = build_timeline(body, snapshot)["jobs"]
    assert [(j["workerId"], j["status"], j["reward"]) for j in jobs if j["candidateId"] == "r.g0.c0"] == [
        ("a", "FAILED", None),
        ("b", "SUCCEEDED", 0.5),
    ]


def test_a_running_attempt_has_no_end_and_pending_candidates_are_counted_not_invented():
    body, snapshot = synthetic()
    timeline = build_timeline(body, snapshot)
    running = [j for j in timeline["jobs"] if j["status"] == "RUNNING"]
    assert len(running) == 1 and running[0]["endMs"] is None and running[0]["workerId"] == "a"
    assert len(timeline["jobs"]) == 3
    [generation] = timeline["generations"]
    assert (
        generation["candidateCount"] == 3
        and generation["committedCount"] == 1
        and generation["doneMs"] is None
        and generation["evaluatedMs"] is None
    )


def test_generation_times_fall_back_to_the_recorded_dates_when_events_are_missing():
    body, snapshot = synthetic()
    snapshot["events"] = []
    [generation] = build_timeline(body, snapshot)["generations"]
    assert generation["openMs"] == 1791619205000


def test_only_meaningful_moments_become_marks_and_they_are_time_ordered():
    body, snapshot = synthetic()
    marks = build_timeline(body, snapshot)["marks"]
    assert [(m["type"], m["workerId"]) for m in marks] == [("replay", "b")], "routine step events never become marks"
    snapshot["events"] += [
        {"event": "worker_unavailable", "t": 1791619207.0, "worker_id": "a"},
        {"event": "managed_error", "t": 1791619208.0, "error": "boom"},
    ]
    marks = build_timeline(body, snapshot)["marks"]
    assert [m["type"] for m in marks] == ["worker_unavailable", "managed_error", "replay"]


def test_an_empty_or_odd_snapshot_never_raises_and_stays_valid_json():
    for snapshot in ({}, {"state": {}}, {"generations": [], "candidates": [], "attempts": [], "events": []}):
        timeline = build_timeline({"experimentId": "x", "name": "n", "status": "QUEUED"}, snapshot)
        assert timeline["jobs"] == [] and timeline["generations"] == [] and timeline["workers"] == []
        json.dumps(timeline, allow_nan=False)
    body, snapshot = synthetic()
    snapshot["attempts"][0]["startedAt"] = "not a date"
    snapshot["generations"][0]["rewardMean"] = float("nan")
    json.dumps(build_timeline(body, snapshot), allow_nan=False)


def test_the_view_is_compact_enough_to_stream_every_second():
    size = len(json.dumps(build_timeline(FIXTURE["body"], FIXTURE["snapshot"])))
    assert size < len(json.dumps(FIXTURE["snapshot"])) / 3


def test_jobs_are_ordered_by_start_time_whatever_order_the_ledger_lists_them_in():
    body, snapshot = synthetic()
    snapshot["attempts"].reverse()
    starts = [j["startMs"] for j in build_timeline(body, snapshot)["jobs"]]
    assert starts == sorted(starts) and len(starts) == 3


def test_audit_mismatch_and_quarantine_are_timeline_marks():
    body = FIXTURE["body"]
    snapshot = {
        **FIXTURE["snapshot"],
        "events": [
            {"event": "audit_mismatch", "worker_id": "auditor", "candidate_id": "r/g0/c0", "t": 100},
            {"event": "audit_worker_quarantined", "worker_id": "auditor", "t": 101},
        ],
    }
    shown = build_timeline(body, snapshot)
    assert {m["type"] for m in shown["marks"]} >= {"audit_mismatch", "audit_worker_quarantined"}
