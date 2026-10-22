"""Small tables a notebook shows next to the dashboard: who did how much work, how long generations took, which audits
ran. Pure functions over a lab timeline and its events; `html_table` renders a list of dicts without pandas."""

from html import escape


def work_split(timeline, names=None):
    """One row per generation: committed candidates per device, plus the generation's wall seconds and mean reward."""
    names = names or {}
    workers = [w["id"] for w in timeline.get("workers") or []]
    rows = []
    for g in timeline.get("generations") or []:
        counts = {names.get(w, w): 0 for w in workers}
        for job in timeline.get("jobs") or []:
            if job.get("generation") == g["index"] and job.get("reward") is not None:
                name = names.get(job["workerId"], job["workerId"])
                counts[name] = counts.get(name, 0) + 1
        seconds = (g.get("seconds") or {}).get("total")
        rows.append(
            {
                "generation": g["index"] + 1,
                **counts,
                "seconds": None if seconds is None else round(seconds, 1),
                "mean reward": None if g.get("rewardMean") is None else round(g["rewardMean"], 4),
            }
        )
    return rows


def device_totals(timeline, names=None):
    """Per device: committed candidates, failed attempts, and mean seconds per committed candidate."""
    names = names or {}
    totals = {}
    for job in timeline.get("jobs") or []:
        entry = totals.setdefault(job["workerId"], {"committed": 0, "failed or lost": 0, "busy seconds": 0.0})
        if job.get("reward") is not None:
            entry["committed"] += 1
            if job.get("endMs") is not None:
                entry["busy seconds"] += (job["endMs"] - job["startMs"]) / 1000
        elif job.get("endMs") is not None:
            entry["failed or lost"] += 1
    order = list(dict.fromkeys([w["id"] for w in timeline.get("workers") or []] + list(totals)))
    rows = []
    for worker in order:
        entry = totals.get(worker, {"committed": 0, "failed or lost": 0, "busy seconds": 0.0})
        per = entry["busy seconds"] / entry["committed"] if entry["committed"] else None
        rows.append(
            {
                "device": names.get(worker, worker),
                "committed": entry["committed"],
                "failed or lost": entry["failed or lost"],
                "seconds per candidate": None if per is None else round(per, 1),
            }
        )
    return rows


def audits(events, names=None):
    names = names or {}
    return [
        {
            "candidate": (e.get("details") or {}).get("candidate_id"),
            "re-run by": names.get(e.get("workerId"), e.get("workerId")),
            "matched": e["eventType"] == "audit_completed",
        }
        for e in events
        if e.get("eventType") in ("audit_completed", "audit_mismatch")
    ]


def membership(timeline, names=None):
    names = names or {}
    origin = (timeline.get("experiment") or {}).get("startedMs") or 0
    return [
        {
            "at (s)": round((m["atMs"] - origin) / 1000, 1),
            "device": names.get(m.get("workerId"), m.get("workerId")),
            "event": m["type"],
        }
        for m in timeline.get("marks") or []
        if m["type"]
        in ("worker_joined", "worker_left", "membership_changed", "membership_refused", "worker_unavailable")
    ]


DEFERRED = {409: "not ON (yet)", 403: "not in the run", 503: "away from the lab", None: "not reachable"}
LIFECYCLE = {
    "worker_unavailable": "not reachable at start",
    "worker_restart_deferred": "cannot start yet: asked again in 30 s",
    "worker_restarted": "worker started again",
    "worker_left": "worker stopped (left)",
    "worker_joined": "worker started (new member)",
    "worker_lost": "given up as lost",
    "worker_restart_limit": "too many restarts: left alone",
}


def member_story(lifecycle, ledger_membership, names=None, origin_ms=0, lost=(), silent=None):
    """Who left, died and came back, in time order: the coordinator's own lifecycle log (process side) merged with the
    ledger's membership records (the JOIN/LEAVE that the update math sees). The lab timeline alone cannot tell this: a
    re-added member was `worker_restarted`, never `worker_joined`, before candidate13 (RESULTS.md, finding 9).

    Before candidate13 the coordinator logged nothing when a machine just stopped answering (finding 11; now
    `worker_unreachable`), so two more sources show a drop-out: `lost`, the
    ledger's attempts {workerId, leasedAt, deadline} that never returned, and `silent`, the coordinator's current
    {worker id: unreachable since} for members not answering now."""
    names = names or {}

    def what(e):
        if e["event"] == "worker_restart_deferred":
            return f"{DEFERRED.get(e.get('httpStatus'), 'refused')}: asked again in 30 s"
        return LIFECYCLE[e["event"]]

    rows = [
        (e["t"], names.get(e["worker_id"], e["worker_id"]), "coordinator", what(e), e.get("launch"))
        for e in lifecycle
        if e.get("event") in LIFECYCLE
    ]
    rows += [
        (m["at"], names.get(m["workerId"], m["workerId"]), "ledger", f"{m['action']} from generation {m['generation'] + 1}", None)
        for m in ledger_membership
        if m["actor"] != "experiment"  # the initial members, all at generation 0
    ]  # fmt: skip
    rows += [
        (a["deadline"], names.get(a["workerId"], a["workerId"]), "ledger", "work lost: no answer by its deadline", None)
        for a in lost
    ]
    rows += [
        (since, names.get(w, w), "coordinator", "not answering (still, at this snapshot)", None)
        for w, since in (silent or {}).items()
    ]
    return [
        {"at (min)": round((t - origin_ms / 1000) / 60, 1), "device": device, "source": source, "what": what, "launch": launch}
        for t, device, source, what, launch in sorted(rows, key=lambda r: r[0])
    ]  # fmt: skip


def html_table(rows, caption=None):
    if not rows:
        return "<p><em>none</em></p>"
    columns = list(dict.fromkeys(k for row in rows for k in row))
    head = "".join(f"<th>{escape(str(c))}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{'' if row.get(c) is None else escape(str(row.get(c)))}</td>" for c in columns) + "</tr>"
        for row in rows
    )
    title = f"<caption style='text-align:left'>{escape(caption)}</caption>" if caption else ""
    return f"<table>{title}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
