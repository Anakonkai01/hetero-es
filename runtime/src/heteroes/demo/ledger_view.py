"""A run's timeline rebuilt from the coordinator's own files, in the shape of the lab's (backend/timeline.py).

The lab's timeline of a long run loses its attempts (RESULTS.md finding 10: the coordinator bounds what it sends), so the
dashboard and the replay of such a run are drawn from the ledger (every attempt, result and update) and the coordinator's
event log (generation open/done times, audits, validation, membership) instead. Read-only.
"""

import json
from pathlib import Path
import sqlite3


def _events(run_dir):
    out = []
    for line in (Path(run_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a line being written
    return out


def ledger_timeline(run_dir, now_s, name=None, max_generations=None, population=None):
    """The timeline at `now_s` (seconds); `name`, `max_generations` and `population` label it like the lab does."""
    run_dir = Path(run_dir)
    run_id = run_dir.name
    events = _events(run_dir)
    db = sqlite3.connect(f"file:{run_dir / 'ledger.sqlite'}?mode=ro", uri=True)
    try:
        rows = db.execute(
            """SELECT a.candidate_id, c.generation, a.attempt_number, a.worker_id, a.leased_at, a.ended_at, a.deadline,
                      a.failure_kind, r.reward
               FROM attempt a JOIN candidate c ON c.candidate_id = a.candidate_id
               LEFT JOIN result r ON r.candidate_id = a.candidate_id AND r.attempt_number = a.attempt_number
               ORDER BY a.leased_at"""
        ).fetchall()
    finally:
        db.close()

    def ms(seconds):
        return None if seconds is None else int(seconds * 1000)

    jobs = []
    for candidate, generation, number, worker, leased, ended, deadline, failure, reward in rows:
        if reward is not None:
            status = "SUCCEEDED"
        elif ended is not None:
            status = "FAILED"
        else:
            status = "RUNNING" if deadline >= now_s else "LOST"
        jobs.append(
            {
                "candidateId": candidate,
                "attemptId": f"{candidate}.a{number}",
                "generation": generation,
                "workerId": worker,
                "startMs": ms(leased),
                "endMs": ms(ended if ended is not None else (deadline if status == "LOST" else None)),
                "status": status,
                "reward": reward,
            }
        )
    opened = {e["generation"]: e["t"] for e in events if e.get("event") == "generation_open"}
    done = {e["generation"]: e["t"] for e in events if e.get("event") == "update_applied"}
    rewards = {}
    for job in jobs:
        if job["reward"] is not None:
            rewards.setdefault(job["generation"], []).append(job["reward"])
    generations = [
        {
            "index": g,
            "status": "COMPLETED" if g in done else "RUNNING",
            "openMs": ms(opened[g]),
            "doneMs": ms(done.get(g)),
            "committedCount": len(rewards.get(g, [])),
            "rewardMean": sum(rewards[g]) / len(rewards[g]) if g in done and rewards.get(g) else None,
            "rewardBest": max(rewards[g]) if g in done and rewards.get(g) else None,
            "seconds": {},
        }
        for g in sorted(opened)
    ]
    config = json.loads((run_dir / "config.json").read_text())
    start = next((e["t"] for e in events if e.get("event") == "managed_start"), min(opened.values(), default=now_s))
    return {
        "experiment": {
            "id": run_id,
            "name": name,
            "status": "RUNNING",
            "startedMs": ms(start),
            "maxGenerations": max_generations,
            "candidatesPerGeneration": population,
        },
        "workers": [{"id": w} for w in config.get("workerIds", [])],
        "generations": generations,
        "jobs": jobs,
        "marks": [],
        "nowMs": ms(now_s),
    }


def ledger_events(run_dir):
    """The coordinator's audits, validations and membership changes, shaped as `heteroes.demo.lab.coordinator_events`."""
    kinds = ("audit_completed", "audit_mismatch", "validation_completed", "worker_joined", "worker_left")
    return [
        {"eventType": e["event"], "workerId": e.get("worker_id"), "details": e}
        for e in _events(run_dir)
        if e.get("event") in kinds + ("membership_changed",)
    ]
