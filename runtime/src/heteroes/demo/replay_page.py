"""A self-contained HTML page that replays a recorded run in a browser (phone included).

The page holds a compact recording (one row per attempt, generation, audit and membership change) and draws every moment
itself, so a 300-generation night stays a few hundred kilobytes. The template is `replay_template.html` beside this file.
"""

import json
from pathlib import Path

from heteroes.demo.dashboard import SERIES

TEMPLATE = Path(__file__).with_name("replay_template.html")


def recording(timeline, events=(), names=None, coordinator=None, title=None):
    """The compact, anonymous recording of a run: device names, times in seconds from the start, rewards, audits."""
    names = names or {}
    experiment = timeline.get("experiment") or {}
    jobs = [j for j in timeline.get("jobs") or [] if j.get("startMs") is not None]
    origin = experiment.get("startedMs") or min((j["startMs"] for j in jobs), default=timeline.get("nowMs") or 0)
    end = experiment.get("completedMs") or timeline.get("nowMs") or origin
    order = [w["id"] for w in timeline.get("workers") or []]
    order += [j["workerId"] for j in jobs if j.get("workerId") and j["workerId"] not in order]
    order = list(dict.fromkeys(order))
    index = {w: i for i, w in enumerate(order)}

    def s(ms):
        return None if ms is None else round((ms - origin) / 1000, 2)

    lanes = [
        [index[j["workerId"]], s(j["startMs"]), s(j.get("endMs")), j.get("generation"),
         1 if j.get("reward") is not None else (0 if j.get("endMs") is not None else -1), j.get("reward")]  # fmt: skip
        for j in jobs
        if j.get("workerId") in index
    ]
    generations = [
        [g["index"], s(g["doneMs"]), g.get("rewardMean"), g.get("rewardBest")]
        for g in timeline.get("generations") or []
        if g.get("doneMs") is not None
    ]
    validation, audits, membership = [], [], []
    changes = {"worker_joined": "joined", "worker_left": "left", "membership_changed": "changed"}
    for event in events:
        kind = event.get("eventType") or event.get("event")
        details = event.get("details") or event
        if details.get("t") is None:
            continue
        at = s(details["t"] * 1000)
        worker = index.get(details.get("worker_id"))
        if kind == "validation_completed":
            validation.append([details.get("generation"), at, details.get("meanReward")])
        elif kind in ("audit_completed", "audit_mismatch") and worker is not None:
            audits.append([at, worker, kind == "audit_completed"])
        elif kind in changes and worker is not None:
            membership.append([at, worker, changes[kind]])
    return {
        "title": title or experiment.get("name") or "HeteroES run",
        "status": experiment.get("status"),
        "coordinator": coordinator,
        "total": experiment.get("maxGenerations"),
        "population": experiment.get("candidatesPerGeneration"),
        "duration": s(end) or 0,
        "devices": [{"name": names.get(w, w), "color": SERIES[i % len(SERIES)]} for i, w in enumerate(order)],
        "lanes": lanes,
        "generations": generations,
        "validation": sorted(validation, key=lambda v: v[1]),
        "audits": sorted(audits),
        "membership": sorted(membership),
    }


def write_page(record, path):
    data = json.dumps(record, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    Path(path).write_text(TEMPLATE.read_text(encoding="utf-8").replace("/*RECORDING*/null", data), encoding="utf-8")
    return path
