"""A compact, time-ordered view of one run for the Live, Timeline and Replay screens.

Pure: it reads the stored snapshot and returns plain data, so a finished run and a running one are described the
same way. Times are epoch milliseconds; generations are numbered from 0 as in the ledger.
"""

from datetime import datetime
import math
import time

# Moments worth showing on a timeline. Routine chatter (a worker asking for work) is deliberately not a mark.
MARKS = frozenset(
    {
        "replay",
        "worker_unavailable",
        "worker_start_unknown",
        "worker_start",
        "model_loaded",
        "executor_ready",
        "transport_error",
        "coordinator_recovery",
        "recovered",
        "generation_resumed",
        "recovery_point_error",
        "managed_error",
        "audit_mismatch",
        "audit_worker_quarantined",
        "audit_incomplete",
    }
)
SECONDS = (
    ("wait", "wait_seconds"),
    ("update", "update_seconds"),
    ("publish", "publish_seconds"),
    ("record", "record_seconds"),
    ("total", "total_seconds"),
)


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _ms_from_iso(value):
    try:
        return int(datetime.fromisoformat(value).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _ms_from_epoch(value):
    number = _number(value)
    return None if number is None else int(number * 1000)


def _generation_index(generation_id):
    try:
        return int(str(generation_id).rsplit(".g", 1)[1])
    except (IndexError, ValueError):
        return None


def build_timeline(body, snapshot, now_ms=None):
    snapshot = snapshot or {}
    state = snapshot.get("state") or {}
    events = sorted(
        (e for e in snapshot.get("events") or [] if isinstance(e, dict) and _number(e.get("t")) is not None),
        key=lambda e: e["t"],
    )
    candidates = {c.get("candidateId"): c for c in snapshot.get("candidates") or []}

    jobs = []
    for item in snapshot.get("attempts") or []:
        start = _ms_from_iso(item.get("startedAt"))
        if start is None:
            continue
        candidate = candidates.get(item.get("candidateId"), {})
        won = (
            candidate.get("status") == "COMMITTED"
            and candidate.get("attemptId") == item.get("attemptId")
            and item.get("status") == "SUCCEEDED"
        )
        jobs.append(
            {
                "candidateId": item.get("candidateId"),
                "attemptId": item.get("attemptId"),
                "generation": _generation_index(item.get("generationId")),
                "workerId": item.get("workerId"),
                "seed": candidate.get("seed"),
                "startMs": start,
                "endMs": _ms_from_iso(item.get("completedAt")),
                "status": item.get("status"),
                "reward": _number(candidate.get("reward")) if won else None,
            }
        )
    jobs.sort(key=lambda j: (j["startMs"], j["candidateId"] or ""))

    by_generation = {}
    for event in events:
        index = event.get("generation")
        if isinstance(index, int) and event.get("event") in (
            "generation_open",
            "generation_complete",
            "generation_done",
        ):
            by_generation.setdefault(index, {})[event["event"]] = event
    generations = []
    for item in snapshot.get("generations") or []:
        index = _generation_index(item.get("generationId"))
        if index is None:
            continue
        seen = by_generation.get(index, {})
        done = seen.get("generation_done", {})
        finished = item.get("status") == "COMPLETED"
        seconds = {name: _number(done.get(key)) for name, key in SECONDS if _number(done.get(key)) is not None}
        generations.append(
            {
                "index": index,
                "id": item.get("generationId"),
                "status": item.get("status"),
                "openMs": _ms_from_epoch(seen.get("generation_open", {}).get("t"))
                or _ms_from_iso(item.get("startedAt")),
                "evaluatedMs": _ms_from_epoch(seen.get("generation_complete", {}).get("t")),
                "doneMs": _ms_from_epoch(done.get("t"))
                or (_ms_from_iso(item.get("completedAt")) if finished else None),
                "candidateCount": item.get("candidateCount"),
                "committedCount": item.get("committedCandidateCount"),
                "rewardMean": _number(item.get("rewardMean", done.get("mean_reward"))),
                "rewardBest": _number(item.get("rewardBest", done.get("max_reward"))),
                "seconds": seconds,
            }
        )
    generations.sort(key=lambda g: g["index"])

    workers, known = [], set()
    for worker_id, info in (state.get("workerStates") or {}).items():
        known.add(worker_id)
        workers.append(
            {"id": worker_id, "started": not (info or {}).get("notStarted", False), "alive": (info or {}).get("alive")}
        )
    for job in jobs:
        if job["workerId"] and job["workerId"] not in known:
            known.add(job["workerId"])
            workers.append({"id": job["workerId"], "started": True, "alive": None})

    marks = []
    for event in events:
        if event.get("event") in MARKS:
            mark = {
                "atMs": int(event["t"] * 1000),
                "type": event["event"],
                "workerId": event.get("worker_id"),
                "generation": event.get("generation"),
            }
            if isinstance(event.get("error"), str):
                mark["detail"] = event["error"][:200]
            marks.append(mark)

    body = body or {}
    started = _ms_from_epoch(state.get("startedAt")) or _ms_from_iso(body.get("startedAt"))
    completed = _ms_from_epoch(state.get("completedAt")) or _ms_from_iso(body.get("completedAt"))
    return {
        "experiment": {
            "id": body.get("experimentId"),
            "name": body.get("name"),
            "status": state.get("status") or body.get("status"),
            "createdMs": _ms_from_iso(body.get("createdAt")),
            "startedMs": started,
            "completedMs": completed,
            "maxGenerations": body.get("maxGenerations"),
            "candidatesPerGeneration": body.get("candidatesPerGeneration"),
        },
        "workers": workers,
        "generations": generations,
        "jobs": jobs,
        "marks": marks,
        "nowMs": int(time.time() * 1000) if now_ms is None else now_ms,
    }
