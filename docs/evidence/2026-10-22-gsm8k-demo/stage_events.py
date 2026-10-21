"""Tier 2's declared events, performed once each and logged: quang-3060 OFF when generation index 2 opens, ON when index 3
opens; each step must show its effect within its deadline (README.md, "Declared events").

    python stage_events.py <out operator-events.jsonl> [tier] [--add]

`--add` (tier 2b, PREDECLARATION-tier2b.md): with ON, the owner also adds the worker back to the experiment, the product's
rejoin path (a worker that left is never auto-joined again, ADR-009); the rejoin deadline is then 15 minutes.
"""

import json
import sys
import time

from heteroes.demo import gsm8k
from heteroes.demo.lab import DemoLab, TERMINAL, wait_until

QUANG = "cli-73b87e369ddc"
DEADLINE = 600


def main():
    lab = DemoLab()
    tier = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "tier2"
    add = "--add" in sys.argv
    run = gsm8k.run_id(tier)
    out = open(sys.argv[1], "a")

    def log(**entry):
        out.write(json.dumps({"t": round(time.time(), 3), **entry}) + "\n")
        out.flush()

    def opened(index):
        timeline = lab.timeline(run)
        if timeline["experiment"]["status"] in TERMINAL:
            raise RuntimeError("run ended before the declared event")
        return any(g["index"] >= index for g in timeline["generations"])

    def events(kind):  # the timeline's marks carry membership changes; the lab-wide event feed is too slow to poll
        return [m for m in lab.timeline(run)["marks"] if m["type"] == kind and m.get("workerId") == QUANG]

    def quang_result_after(at):
        return [
            j for j in lab.timeline(run)["jobs"] if j["workerId"] == QUANG and j["reward"] is not None and j["startMs"] > at
        ]

    try:
        wait_until(lambda: opened(2), 3600, every=5)
        log(event="off_requested", response=lab.set_contribution(QUANG, False))
        start = time.time()
        left = wait_until(lambda: events("worker_left") or events("membership_changed"), DEADLINE, every=5)
        log(event="off_verdict", verdict="recovered", seconds=round(time.time() - start, 1), seen=[m["type"] for m in left])
    except Exception as error:
        log(event="off_verdict", verdict="failed", error=str(error)[:300])
        return
    try:
        wait_until(lambda: opened(3), 3600, every=5)
        on_at = int(time.time() * 1000)
        log(event="on_requested", response=lab.set_contribution(QUANG, True))
        if add:
            body = {"workerId": QUANG, "action": "add"}
            log(event="add_requested", response=lab.request("POST", f"/api/v1/experiments/{run}/workers", body))
        deadline = 900 if add else DEADLINE
        joined = wait_until(lambda: events("worker_joined"), deadline, every=5)
        result = wait_until(lambda: quang_result_after(on_at), deadline - (time.time() - on_at / 1000), every=5)
        log(event="on_verdict", verdict="recovered", seconds=round(time.time() - on_at / 1000, 1),
            joined=len(joined), first_result=result[0]["candidateId"])  # fmt: skip
    except Exception as error:
        log(event="on_verdict", verdict="failed", error=str(error)[:300])


if __name__ == "__main__":
    main()
