"""Save a run's records as the notebook reads them, so the notebook also runs without the lab (a demo room offline):

    python snapshot.py <tier> <out dir>

Writes timeline.json (lab), experiment.json (lab), events.json (the coordinator's own audit/validation/membership log on
this machine), lifecycle.json (its worker process log), membership.json (the ledger's JOIN/LEAVE records),
validation.json (the held-out scores so far), work.json and audits.json (per-device work and every audit, from the
ledger) and devices.json (the lab's member list, self-test fields only). Runs at any moment: a running run gives a mid-run
snapshot. No token or secret is written.
"""

import json
import sqlite3
import sys
import time
from pathlib import Path

from heteroes.demo import gsm8k
from heteroes.demo.lab import COORDINATOR_RUNS, DemoLab, coordinator_events


def device(d):
    """Only what the notebook's member table shows (no hostname, driver path or other self-test detail)."""
    st = d.get("selfTest") or {}
    env = st.get("environment") or {}
    return {
        "workerId": d["workerId"],
        "connectionStatus": d["connectionStatus"],
        "selfTest": {
            "gpuName": st.get("gpuName"),
            "vramTotalMb": st.get("vramTotalMb"),
            "environment": {"platform": env.get("platform"), "torch": env.get("torch")},
        },
    }


def main():
    tier, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    lab, run = DemoLab(), gsm8k.run_id(tier)
    records = {
        "timeline.json": lab.timeline(run),
        "experiment.json": lab.experiment(run),
        "events.json": coordinator_events(run)(),
        "devices.json": [device(d) for d in lab.devices() if d["workerId"] in gsm8k.NAMES],
    }
    root = COORDINATOR_RUNS / run  # the coordinator runs on this machine (5070ti-nhan)
    records["lifecycle.json"] = [
        json.loads(line) for line in (root / "lifecycle.jsonl").read_text().splitlines() if line
    ]
    ledger = sqlite3.connect(f"file:{root / 'ledger.sqlite'}?mode=ro", uri=True)
    records["membership.json"] = [
        {"workerId": w, "action": a, "generation": g, "actor": actor, "at": at}
        for w, a, g, actor, at in ledger.execute(
            "SELECT worker_id, action, effective_generation, actor, recorded_at FROM membership ORDER BY recorded_at"
        )
    ]
    # the lab's timeline keeps only the newest attempts of a long run (the coordinator bounds what it sends, 1.25 MB), so
    # the per-device work and the audits are counted from the ledger, which holds them all
    work = ledger.execute(
        """SELECT a.worker_id, count(r.candidate_id),
                  sum(CASE WHEN r.candidate_id IS NULL AND (a.ended_at IS NOT NULL OR a.deadline < ?) THEN 1 ELSE 0 END),
                  sum(CASE WHEN r.candidate_id IS NOT NULL THEN a.ended_at - a.leased_at END)
           FROM attempt a LEFT JOIN result r ON r.candidate_id = a.candidate_id AND r.attempt_number = a.attempt_number
           GROUP BY a.worker_id ORDER BY 2 DESC""",
        (time.time(),),
    )  # an attempt without a result whose lease ran out was lost with its machine
    records["work.json"] = [
        {"device": gsm8k.NAMES.get(w, w), "committed": n, "failed or lost": lost,
         "seconds per candidate": round(busy / n, 1) if n else None}
        for w, n, lost, busy in work
    ]  # fmt: skip
    records["lost.json"] = [
        {"workerId": w, "leasedAt": leased, "deadline": deadline}
        for w, leased, deadline in ledger.execute(
            """SELECT a.worker_id, a.leased_at, a.deadline FROM attempt a LEFT JOIN result r
               ON r.candidate_id = a.candidate_id AND r.attempt_number = a.attempt_number
               WHERE r.candidate_id IS NULL AND a.ended_at IS NULL AND a.deadline < ? ORDER BY a.leased_at""",
            (time.time(),),
        )
    ]
    workers = json.loads((root / "state.json").read_text()).get("workerStates") or {}
    records["silent.json"] = {w: v["unreachableSince"] for w, v in workers.items() if v.get("unreachableSince")}
    records["audits.json"] = [
        {"candidate": c, "re-run by": gsm8k.NAMES.get(w, w), "matched": bool(m)}
        for c, w, m in ledger.execute("SELECT candidate_id, worker_id, matched FROM audit ORDER BY audited_at")
    ]
    validations = sorted(root.glob("validation-*.json"), key=lambda p: int(p.stem.split("validation-")[1]))
    records["validation.json"] = [
        {
            k: v
            for k, v in json.loads(p.read_text()).items()
            if k in ("generation", "meanReward", "count", "weightsSha256")
        }
        for p in validations
    ]
    for name, value in records.items():
        (out / name).write_text(json.dumps(value, indent=1))
    t = records["timeline.json"]
    print(run, t["experiment"]["status"], "generations", len(t["generations"]), "jobs", len(t["jobs"]))


if __name__ == "__main__":
    main()
