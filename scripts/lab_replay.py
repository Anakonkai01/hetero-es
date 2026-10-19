"""Reveal a recorded run (as exported from a real lab) bit by bit, as if it were running now.

Used by scripts/serve-test-lab.py --simulate-live so the Live screens can be exercised end to end without a GPU.
`reveal(recording, now_epoch_seconds)` is pure: it returns the (body, snapshot) the lab would have stored at that moment.
"""

from datetime import datetime, timedelta
import copy


def _epoch(iso):
    return datetime.fromisoformat(iso).timestamp() if iso else None


def reveal(recording, now):
    body = copy.deepcopy(recording["body"])
    full = recording["snapshot"]
    state = full["state"]
    if now >= state["completedAt"]:
        return body, copy.deepcopy(full)
    snapshot = copy.deepcopy(full)
    body.update(status="RUNNING")
    for key in ("completedAt", "failureReason"):
        body.pop(key, None)
    snapshot["state"] = {**state, "status": "RUNNING"}
    for key in ("completedAt", "finalWeightsSha256"):
        snapshot["state"].pop(key, None)
    snapshot["events"] = [e for e in full["events"] if e.get("t", 0) <= now]

    attempts = []
    for item in full["attempts"]:
        started = _epoch(item.get("startedAt"))
        if started is None or started > now:
            continue
        item = copy.deepcopy(item)
        completed = _epoch(item.get("completedAt"))
        if completed is None or completed > now:
            item.update(status="RUNNING", completedAt=None, errorType=None)
        attempts.append(item)
    snapshot["attempts"] = attempts

    opened = {}
    for generation in full["generations"]:
        started = _epoch(generation.get("startedAt"))
        if started is not None and started <= now:
            opened[generation["generationId"]] = generation
    candidates = []
    for candidate in full["candidates"]:
        if candidate["generationId"] not in opened:
            continue
        candidate = copy.deepcopy(candidate)
        mine = [a for a in attempts if a["candidateId"] == candidate["candidateId"]]
        won = next(
            (a for a in mine if a["attemptId"] == candidate.get("attemptId") and a["status"] == "SUCCEEDED"), None
        )
        running = next((a for a in mine if a["status"] == "RUNNING"), None)
        if won:
            candidate["status"] = "COMMITTED"
        elif running:
            candidate.update(
                status="RUNNING", workerId=running["workerId"], attemptId=running["attemptId"], reward=None
            )
        else:
            candidate.update(status="PENDING", reward=None)
            for key in ("workerId", "attemptId", "leaseDeadline", "leaseToken"):
                candidate.pop(key, None)
        candidates.append(candidate)
    snapshot["candidates"] = candidates

    generations = []
    for generation in opened.values():
        generation = copy.deepcopy(generation)
        committed = sum(
            c["status"] == "COMMITTED" for c in candidates if c["generationId"] == generation["generationId"]
        )
        completed = _epoch(generation.get("completedAt"))
        if completed is not None and completed <= now:
            generations.append(generation)
        else:
            for key in ("completedAt", "rewardMean", "rewardBest"):
                generation.pop(key, None)
            generation.update(status="RUNNING", committedCandidateCount=committed)
            generations.append(generation)
    snapshot["generations"] = generations
    finished = [g for g in generations if g["status"] == "COMPLETED"]
    body["completedGenerations"] = len(finished)
    snapshot["completedGenerationCount"] = len(finished)
    if generations:
        body["currentGenerationId"] = generations[-1]["generationId"]
        body["committedCandidateCount"] = generations[-1].get("committedCandidateCount", 0)
    snapshot.pop("latestGeneration", None)
    return body, snapshot


def shift(recording, seconds):
    """A copy of the recording with every time moved by `seconds`, so a run recorded days ago can start "now"."""

    def move(value):
        if isinstance(value, dict):
            return {key: (shift_time(item) if _is_time_key(key) else move(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [move(item) for item in value]
        return value

    def shift_time(value):
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return value + seconds
        if isinstance(value, str):
            try:
                return (datetime.fromisoformat(value) + timedelta(seconds=seconds)).isoformat()
            except ValueError:
                return value
        return move(value)

    return move(copy.deepcopy(recording))


def _is_time_key(key):
    return key == "t" or key == "leaseDeadline" or (key.endswith("At") and key != "format")
