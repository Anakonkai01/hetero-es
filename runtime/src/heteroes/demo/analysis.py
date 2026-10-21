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
