"""Detached operator monitor for the candidate7 managed acceptance (runs on the 5070).

Every 10 s it reads the coordinator's ledger (snapshot.py over SSH, read-only) and the lab, and performs the declared
events once each: the 1660S joins at >= g10, Thao's Windows Worker is hard-stopped at >= g19 while it holds an active
main lease and relaunched ~300 s later (contribution ON for the new boot), the 1660S leaves at >= g30. An audit mismatch
or a quarantine requests PAUSE and stops the monitor. `decide` is pure so the event logic is tested without machines.

    python3 monitor.py <experiment id>
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/pc5070ti/projects/heteroes")
EVIDENCE = ROOT / "docs/evidence/2026-10-21-long-multimachine-run-candidate7"
HELPERS = ROOT / ".scratch/r11-c7-run"
WORKSPACE = "bcbece5a24834ac28e358fc49db1343f"
THAO = "thao_nguyen@100.92.20.58"
JOINER = "cli-3e355c6e9e70"
FAILED = "desktop-9f9da13f0f82"
JOIN_AT, FAULT_AT, LEAVE_AT, OUTAGE = 10, 19, 30, 300
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "PAUSED")


def decide(flags, snap, status, now):
    """The actions due now, given what was already done (`flags`), a ledger snapshot and the lab's status."""
    if (snap.get("audits", [0, 0])[1] or snap.get("quarantines")) and not flags.get("pauseRequested"):
        return ["pause"]
    if status in TERMINAL:
        return ["finish"]
    applied = snap.get("applied", 0)
    actions = []
    if applied >= JOIN_AT and not flags.get("joined"):
        actions.append("join")
    if applied >= FAULT_AT and not flags.get("stoppedAt") and (snap.get("active") or {}).get(FAILED):
        actions.append("fault")
    if flags.get("stoppedAt") and not flags.get("relaunched") and now - flags["stoppedAt"] >= OUTAGE:
        actions.append("relaunch")
    if flags.get("relaunched") and not flags.get("contributionOn"):
        actions.append("contribution")
    if applied >= LEAVE_AT and flags.get("joined") and not flags.get("left"):
        actions.append("leave")
    return actions


def ssh(host, command, timeout=60):
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, command],
        capture_output=True, text=True, timeout=timeout,
    )
    if p.returncode:
        raise RuntimeError(f"SSH failed ({p.returncode}): " + p.stderr[:200])
    return p.stdout


def powershell(script, timeout=180):
    p = subprocess.run(
        [sys.executable, str(ROOT / ".scratch/windows-system-finish/run-ps.py"), str(script)],
        capture_output=True, text=True, timeout=timeout,
    )
    if p.returncode:
        raise RuntimeError(f"PowerShell failed ({p.returncode}): " + (p.stderr or p.stdout)[:300])
    return p.stdout


def log(name, body):
    with (EVIDENCE / name).open("a") as stream:
        stream.write(json.dumps(body) + "\n")


def main(experiment):
    sys.path.insert(0, str(ROOT / ".scratch/isolated-lab"))
    import os

    os.chdir(ROOT / ".scratch/isolated-lab")  # api.py reads secret/ relative to here
    import api

    def call(method, path, body=None):
        return api.call(method, path, body, api.login("researcher"), workspace=WORKSPACE)

    flags = {}
    failures = 0
    while True:
        try:
            snap = json.loads(ssh(THAO, f"python3 /tmp/heteroes-r11-c7/snapshot.py {experiment} {FAILED},{JOINER}"))
            code, body = call("GET", f"/api/v1/experiments/{experiment}")
            status = body.get("status") if isinstance(body, dict) else None
            snap["labStatus"] = status
            log("monitor.jsonl", snap)
            failures = 0
            now = time.time()
            for action in decide(flags, snap, status, now):
                if action == "pause":
                    code, body = call("POST", f"/api/v1/experiments/{experiment}/pause")
                    flags["pauseRequested"] = True
                    log("operator-events.jsonl", {"event": "STOP_AUDIT_PAUSE", "t": now, "httpStatus": code,
                                                  "audits": snap.get("audits"), "quarantines": snap.get("quarantines")})
                elif action == "finish":
                    log("operator-events.jsonl", {"event": "terminal", "t": now, "status": status})
                    return 0 if status == "COMPLETED" else 1
                elif action in ("join", "leave"):
                    request = {"workerId": JOINER, "action": "add" if action == "join" else "remove"}
                    code, body = call("POST", f"/api/v1/experiments/{experiment}/workers", request)
                    log("operator-events.jsonl", {"event": action, "t": now, "applied": snap.get("applied"),
                                                  "httpStatus": code, "reply": body})
                    if code == 200:
                        flags["joined" if action == "join" else "left"] = now
                elif action == "fault":
                    flags["stoppedAt"] = now  # set first: a failure after the stop must still lead to the relaunch
                    receipt = json.loads(powershell(HELPERS / "fault-windows.ps1").strip().splitlines()[-1])
                    log("operator-events.jsonl", {"event": "injected", "t": now, "applied": snap.get("applied"),
                                                  "activeLease": snap["active"][FAILED], "receipt": receipt})
                elif action == "relaunch":
                    # The launch control keeps its session open after the app starts; it is not waited for.
                    subprocess.Popen(
                        [sys.executable, str(ROOT / ".scratch/windows-system-finish/run-ps.py"),
                         str(ROOT / ".scratch/windows-system-finish/launch-c7.ps1")],
                        stdout=open(HELPERS / "relaunch.log", "a"), stderr=subprocess.STDOUT, start_new_session=True,
                    )
                    flags["relaunched"] = now
                    log("operator-events.jsonl", {"event": "relaunch_requested", "t": now,
                                                  "outageSeconds": now - flags["stoppedAt"]})
                elif action == "contribution":
                    code, devices = call("GET", "/api/v1/devices")
                    device = next(d for d in devices if d["workerId"] == FAILED)
                    if device["connectionStatus"] == "ONLINE" and device["contributionEnabled"]:
                        flags["contributionOn"] = now
                    elif device["connectionStatus"] == "ONLINE":
                        code, _ = call("POST", f"/api/v1/devices/{device['deviceId']}/contribution",
                                       {"enabled": True, "bootId": device["bootId"]})
                        log("operator-events.jsonl", {"event": "restart_contribution_on", "t": now, "httpStatus": code})
                        if code == 200:
                            flags["contributionOn"] = now
        except Exception as error:  # one failed read or action is retried on the next round
            failures += 1
            log("operator-events.jsonl", {"event": "monitor_error", "t": time.time(), "error": str(error)[:300],
                                          "consecutive": failures})
        time.sleep(10)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
