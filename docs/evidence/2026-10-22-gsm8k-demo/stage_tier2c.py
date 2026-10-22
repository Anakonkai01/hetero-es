"""Tier 2c's declared events (PREDECLARATION-tier2c.md), each performed once and logged:

    python stage_tier2c.py <out jsonl>

(c) the 1660s Worker service killed (SIGKILL, every process) when generation index 1 opens and started again by a timer on
that machine 40 minutes later; (b1) 5070ti-nhut OFF when index 2 opens; (b2) ON and added back when index 3 opens. The
release and the 1660s return are judged afterwards from the lab and the coordinator (RESULTS.md).
"""

import json
import subprocess
import sys
import time

from heteroes.demo import gsm8k
from heteroes.demo.lab import DemoLab, TERMINAL, wait_until

NHUT = "cli-aa99b4d4ca58"
SSH_1660S = ["ssh", "-o", "HostKeyAlias=heteroes-worker-1660s", "-o", "BatchMode=yes", "anakonkai@100.119.83.46"]
# the timer is set first, on the machine itself, so the service comes back whatever happens to this script
KILL = (
    "systemd-run --user --on-active=40m --unit=tier2c-revive systemctl --user start heteroes-worker.service"
    " && systemctl --user kill --signal=SIGKILL heteroes-worker.service"
    " && sleep 1 && systemctl --user stop heteroes-worker.service; systemctl --user is-active heteroes-worker.service"
)


def main():
    lab = DemoLab()
    run = gsm8k.run_id("tier2c")
    out = open(sys.argv[1], "a")

    def log(**entry):
        out.write(json.dumps({"t": round(time.time(), 3), **entry}) + "\n")
        out.flush()

    def opened(index):
        timeline = lab.timeline(run)
        if timeline["experiment"]["status"] in TERMINAL:
            raise RuntimeError("run ended before the declared event")
        return any(g["index"] >= index for g in timeline["generations"])

    def marks(kind, worker):
        return [m for m in lab.timeline(run)["marks"] if m["type"] == kind and m.get("workerId") == worker]

    def result_after(worker, at):
        return [
            j
            for j in lab.timeline(run)["jobs"]
            if j["workerId"] == worker and j["reward"] is not None and j["startMs"] > at
        ]

    wait_until(lambda: opened(1), 3600, every=5)
    killed = subprocess.run(SSH_1660S + [KILL], capture_output=True, text=True, timeout=60)
    log(
        event="kill_requested", target="1660s", returncode=killed.returncode, out=(killed.stdout + killed.stderr)[-300:]
    )
    try:
        wait_until(lambda: opened(2), 3600, every=5)
        log(event="off_requested", response=lab.set_contribution(NHUT, False))
        start = time.time()
        left = wait_until(lambda: marks("worker_left", NHUT) or marks("membership_changed", NHUT), 600, every=5)
        log(
            event="off_verdict",
            verdict="recovered",
            seconds=round(time.time() - start, 1),
            seen=[m["type"] for m in left],
        )
    except Exception as error:
        log(event="off_verdict", verdict="failed", error=str(error)[:300])
        return
    try:
        wait_until(lambda: opened(3), 3600, every=5)
        on_at = int(time.time() * 1000)
        log(event="on_requested", response=lab.set_contribution(NHUT, True))
        body = {"workerId": NHUT, "action": "add"}
        log(event="add_requested", response=lab.request("POST", f"/api/v1/experiments/{run}/workers", body))
        joined = wait_until(lambda: marks("worker_joined", NHUT), 900, every=5)
        result = wait_until(lambda: result_after(NHUT, on_at), 900 - (time.time() - on_at / 1000), every=5)
        log(event="on_verdict", verdict="recovered", seconds=round(time.time() - on_at / 1000, 1),
            joined=len(joined), first_result=result[0]["candidateId"])  # fmt: skip
    except Exception as error:
        log(event="on_verdict", verdict="failed", error=str(error)[:300])


if __name__ == "__main__":
    main()
