"""Turn a lab timeline (backend/timeline.py) and the run's events into one Frame: what the dashboard draws at a moment.

Pure and deterministic: no clock, no network. A live run and a recorded one go through the same function, so the replay
shows exactly what the live view showed.
"""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

AUDIT_EVENTS = ("audit_completed", "audit_mismatch")
MEMBER_EVENTS = {"worker_joined": "joined", "worker_left": "left", "membership_changed": "changed"}
ACTIONS = {"JOIN": "joined", "LEAVE": "left"}
SAME_CHANGE_SECONDS = 600  # a process event and its ledger record (worker_left, then LEAVE) are one change


def member_changes(events):
    """(seconds, worker, "joined"/"left") in time order. A re-added member has no `worker_joined`: its JOIN is the
    coordinator's `membership_changed` (ledger) record (RESULTS.md, finding 9), whose worker key is `workerId`. A process
    event and the ledger record of the same change are drawn once."""
    found = []
    for event in events:
        kind = event.get("eventType") or event.get("event")
        details = event.get("details") or event
        if kind not in MEMBER_EVENTS or details.get("t") is None:
            continue
        change = ACTIONS.get(details.get("action"), "changed") if kind == "membership_changed" else MEMBER_EVENTS[kind]
        found.append((details["t"], details.get("worker_id") or details.get("workerId"), change))
    out = []
    for at, worker, change in sorted(found, key=lambda c: c[0]):
        last = next((c for c in reversed(out) if c[1] == worker), None)
        if last is None or last[2] != change or at - last[0] > SAME_CHANGE_SECONDS:
            out.append((at, worker, change))
    return out


@dataclass
class Device:
    worker_id: str
    name: str
    busy: str | None = None  # the candidate it is running now
    alive: bool | None = None
    done: int = 0  # committed candidates over the whole run
    done_now: int = 0  # committed candidates of the newest generation
    audits: int = 0  # audits this device re-ran and matched
    mismatches: int = 0


@dataclass
class Frame:
    at_ms: int
    now_s: float  # seconds since the run started (the right edge of the timeline)
    status: str | None
    generation: int  # the newest generation seen (-1 before the first)
    generations_total: int | None
    devices: list[Device]
    lanes: list[dict]  # {worker, start, end, generation, ok, audit}; times in seconds from the run start
    rewards: list[dict]  # {generation, mean, best, seconds, atS}
    scores: list[float]  # committed rewards of the newest generation that has any
    validation: list[dict]  # {generation, reward}
    audits: dict = field(default_factory=lambda: {"matched": 0, "mismatched": 0})
    membership: list[dict] = field(default_factory=list)  # {atS, worker, change}

    def to_json(self):
        return json.dumps(asdict(self), separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, text):
        value = json.loads(text)
        value["devices"] = [Device(**d) for d in value["devices"]]
        return cls(**value)


def build_frame(timeline, events=(), names=None, at_ms=None):
    """The Frame of `timeline` at `at_ms` (default: the timeline's own `nowMs`).

    `events` are lab events of this run (dicts with `eventType` or `event`, `details`, `timestamp`/`t`); `names` maps a
    worker id to the device name people know. Everything after `at_ms` is left out, which is how a replay advances.
    """
    names = names or {}
    now = timeline.get("nowMs") if at_ms is None else at_ms
    experiment = timeline.get("experiment") or {}
    origin = experiment.get("startedMs") or experiment.get("createdMs") or now or 0

    def seconds(ms):
        return None if ms is None else round((ms - origin) / 1000, 3)

    order = [w["id"] for w in timeline.get("workers") or []]
    for job in timeline.get("jobs") or []:
        if job.get("workerId") and job["workerId"] not in order:
            order.append(job["workerId"])
    devices = {w: Device(w, names.get(w, w)) for w in order}
    completed = experiment.get("completedMs")
    replayed = completed is not None and now < completed
    for w in timeline.get("workers") or []:
        devices[w["id"]].alive = None if replayed else w.get("alive")  # the timeline knows only the latest liveness

    jobs = [j for j in timeline.get("jobs") or [] if j.get("startMs") is not None and j["startMs"] <= now]
    newest = max((j["generation"] for j in jobs if j.get("generation") is not None), default=-1)
    lanes, scores_by_generation = [], {}
    for job in jobs:
        device = devices[job["workerId"]]
        ended = job.get("endMs") is not None and job["endMs"] <= now
        if not ended:
            device.busy = job.get("candidateId")
        elif job.get("reward") is not None:
            device.done += 1
            device.done_now += job.get("generation") == newest
            scores_by_generation.setdefault(job["generation"], []).append(job["reward"])
        lanes.append(
            {
                "worker": job["workerId"],
                "start": seconds(job["startMs"]),
                "end": seconds(job["endMs"]) if ended else None,
                "generation": job.get("generation"),
                "ok": job.get("reward") is not None if ended else None,
                "audit": False,
            }
        )

    rewards = [
        {
            "generation": g["index"],
            "mean": g.get("rewardMean"),
            "best": g.get("rewardBest"),
            "seconds": g.get("seconds"),
            "atS": seconds(g["doneMs"]),
        }
        for g in timeline.get("generations") or []
        if g.get("doneMs") is not None and g["doneMs"] <= now
    ]
    newest = max(
        newest,
        max((g["index"] for g in timeline.get("generations") or [] if (g.get("openMs") or now + 1) <= now), default=-1),
    )
    scored = [g for g in scores_by_generation if scores_by_generation[g]]

    audits, validation = {"matched": 0, "mismatched": 0}, []
    for event in events:
        kind = event.get("eventType") or event.get("event")
        details = event.get("details") or event
        at = details.get("t")
        if at is None or at * 1000 > now:
            continue
        worker = details.get("worker_id")
        if kind in AUDIT_EVENTS:
            matched = kind == "audit_completed"
            audits["matched" if matched else "mismatched"] += 1
            if worker in devices:
                if matched:
                    devices[worker].audits += 1
                else:
                    devices[worker].mismatches += 1
        elif kind == "validation_completed":
            validation.append({"generation": details.get("generation"), "reward": details.get("meanReward")})
    membership = [
        {"atS": seconds(int(at * 1000)), "worker": worker, "change": change}
        for at, worker, change in member_changes(events)
        if at * 1000 <= now
    ]

    status = experiment.get("status")
    if replayed:  # a replayed moment shows the state of that moment
        status = "RUNNING" if newest >= 0 else "STARTING"
    return Frame(
        at_ms=now,
        now_s=seconds(now) or 0.0,
        status=status,
        generation=newest,
        generations_total=experiment.get("maxGenerations"),
        devices=list(devices.values()),
        lanes=lanes,
        rewards=rewards,
        scores=sorted(scores_by_generation[max(scored)]) if scored else [],
        validation=validation,
        audits=audits,
        membership=membership,
    )


def replay_frames(timeline, events=(), names=None, steps=200):
    """`steps` evenly spaced Frames from the run's start to its end (or its `nowMs` while it runs)."""
    experiment = timeline.get("experiment") or {}
    starts = [j["startMs"] for j in timeline.get("jobs") or [] if j.get("startMs") is not None]
    begin = experiment.get("startedMs") or (min(starts) if starts else timeline.get("nowMs") or 0)
    end = experiment.get("completedMs") or timeline.get("nowMs") or begin
    if steps < 2 or end <= begin:
        return [build_frame(timeline, events, names, end)]
    return [build_frame(timeline, events, names, begin + (end - begin) * i // (steps - 1)) for i in range(steps)]


def save_frames(frames, path):
    Path(path).write_text("".join(frame.to_json() + "\n" for frame in frames), encoding="utf-8")


def load_frames(path):
    return [Frame.from_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
