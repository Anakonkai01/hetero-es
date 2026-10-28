"""Detached operator monitor for the candidate9 restart run (runs on the 5070).

Every 10 s it reads the coordinator's ledger (snapshot.py over SSH, read-only) and the lab, and performs the declared
events once each, ONE FAULT AT A TIME: the next one starts only after the previous one has recovered or failed.

  1 JOIN the 1660S (g>=2)
  2 kill -9 Quang's worker process while it holds a lease (g>=5); the agent stays up; it must be started again by itself
  3 LEAVE the 1660S, then JOIN it again once the LEAVE is effective; its worker must be started again by itself
  4 hard-stop Thao's Windows app while it holds a lease, relaunch ~240 s later, contribution ON for the new boot; the
    worker must be started again by itself

A restart that does not happen within 10 minutes is a stop-rule failure; the run itself goes on. An audit mismatch or a
quarantine requests PAUSE. `decide` is pure so the event logic is tested without machines.

    python3 monitor.py <experiment id>
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/pc5070ti/projects/heteroes")
EVIDENCE = ROOT / "docs/evidence/2026-10-21-restart-run-candidate9"
HELPERS = ROOT / ".scratch/r11-c9-run"
WORKSPACE = "bcbece5a24834ac28e358fc49db1343f"
THAO = "thao_nguyen@100.92.20.58"
QUANG_HOST = "quang@100.99.227.8"
JOINER = "cli-3e355c6e9e70"  # GTX 1660 SUPER
WIN = "desktop-9f9da13f0f82"  # Thao native Windows 3060
QUANG = "cli-894b5d440398"  # Quang WSL 3060
LOCAL = "desktop-906949218c43"  # 5070 Ti
WATCH = f"{WIN},{QUANG},{LOCAL},{JOINER}"
JOIN_AT, QUANG_AT, QUANG_SKIP, REJOIN_SKIP, WIN_SKIP, OUTAGE = 2, 5, 20, 30, 36, 240
RESTART_DEADLINE = 600
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "PAUSED")
DONE = ("recovered", "failed", "skipped")


def restart_status(snap, worker, since, base, now):
    """A stopped member must be started again by the system: a `worker_restarted` event after `since`, then new results."""
    restarted = any(e[0] == "worker_restarted" and e[1] == worker and e[3] >= since for e in snap.get("restarts", []))
    produced = snap.get("workers", {}).get(worker, 0) > base
    if restarted and produced:
        return "recovered"
    return "failed" if now - since >= RESTART_DEADLINE else "waiting"


def quang_status(flags, snap, now):
    if "quang" in flags["skipped"]:
        return "skipped"
    if not flags.get("killedAt"):
        return "open"
    return restart_status(snap, QUANG, flags["killedAt"], flags["qBase"], now)


def rejoin_status(flags, snap, now):
    if "rejoin" in flags["skipped"]:
        return "skipped"
    if not flags.get("rejoinedAt"):
        return "open"
    return restart_status(snap, JOINER, flags["rejoinedAt"], flags["jBase"], now)


def win_status(flags, snap, now):
    if "win" in flags["skipped"]:
        return "skipped"
    if not flags.get("stoppedAt"):
        return "open"
    if not flags.get("contributionOn"):  # the app never came back: nothing could be restarted
        relaunched = flags.get("relaunched")
        return "failed" if relaunched and now - relaunched >= RESTART_DEADLINE else "open"
    return restart_status(snap, WIN, flags["contributionOn"], flags["winBase"], now)


def leave_effective(snap):
    """The generation at which the 1660S LEAVE took effect in the ledger, or None."""
    return next((g for w, action, g in snap.get("membership", []) if w == JOINER and action == "LEAVE"), None)


def decide(flags, snap, status, now):
    """The actions due now, given what was already done (`flags`), a ledger snapshot and the lab's status."""
    if (snap.get("audits", [0, 0])[1] or snap.get("quarantines")) and not flags.get("pauseRequested"):
        return ["pause"]
    if status in TERMINAL:
        return ["finish"]
    applied = snap.get("applied", 0)
    active = snap.get("active", {})
    skipped = flags["skipped"]
    actions = []
    if applied >= JOIN_AT and not flags.get("joined"):
        actions.append("join")
    # 2: Quang, the worker process only
    if flags.get("joined") and applied >= QUANG_AT and not flags.get("killedAt") and "quang" not in skipped:
        if applied >= QUANG_SKIP:
            actions.append("skip_quang")
        elif active.get(QUANG):
            actions.append("fault_quang")
    if flags.get("killedAt") and not flags.get("quangVerdict") and quang_status(flags, snap, now) in DONE:
        actions.append("verdict_quang")
    if quang_status(flags, snap, now) not in DONE:
        return actions
    # 3: the 1660S leaves, then joins again once its LEAVE is in the ledger
    if not flags.get("left") and "rejoin" not in skipped:
        actions.append("skip_rejoin" if applied >= REJOIN_SKIP else "leave")
    effective = leave_effective(snap)
    if flags.get("left") and not flags.get("rejoinedAt") and "rejoin" not in skipped:
        if applied >= REJOIN_SKIP:
            actions.append("skip_rejoin")
        elif effective is not None and applied > effective:
            actions.append("rejoin")
    if flags.get("rejoinedAt") and not flags.get("rejoinVerdict") and rejoin_status(flags, snap, now) in DONE:
        actions.append("verdict_rejoin")
    if rejoin_status(flags, snap, now) not in DONE:
        return actions
    # 4: Thao Windows, the whole app
    if not flags.get("stoppedAt") and "win" not in skipped:
        if applied >= WIN_SKIP:
            actions.append("skip_win")
        elif active.get(WIN):
            actions.append("fault_win")
    if flags.get("stoppedAt") and not flags.get("relaunched") and now - flags["stoppedAt"] >= OUTAGE:
        actions.append("relaunch")
    if flags.get("relaunched") and not flags.get("contributionOn"):
        actions.append("contribution")
    if (
        flags.get("stoppedAt")
        and not flags.get("winVerdict")
        and win_status(flags, snap, now) in ("recovered", "failed")
    ):
        actions.append("verdict_win")
    return actions


def ssh(host, command, timeout=60, stdin=None):
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, command],
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=stdin,
    )
    if p.returncode:
        raise RuntimeError(f"SSH failed ({p.returncode}): " + (p.stderr or p.stdout)[:300])
    return p.stdout


def powershell(script, timeout=180):
    p = subprocess.run(
        [sys.executable, str(ROOT / ".scratch/windows-system-finish/run-ps.py"), str(script)],
        capture_output=True,
        text=True,
        timeout=timeout,
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

    def member_change(action):
        return call("POST", f"/api/v1/experiments/{experiment}/workers", {"workerId": JOINER, "action": action})

    flags = {"skipped": []}
    failures = 0
    while True:
        try:
            snap = json.loads(ssh(THAO, f"python3 /tmp/heteroes-r11-c9/snapshot.py {experiment} {WATCH}"))
            code, body = call("GET", f"/api/v1/experiments/{experiment}")
            status = body.get("status") if isinstance(body, dict) else None
            snap["labStatus"] = status
            log("monitor.jsonl", snap)
            failures = 0
            now = time.time()
            for action in decide(flags, snap, status, now):
                applied = snap.get("applied")
                if action == "pause":
                    code, body = call("POST", f"/api/v1/experiments/{experiment}/pause")
                    flags["pauseRequested"] = True
                    log("operator-events.jsonl", {"event": "STOP_AUDIT_PAUSE", "t": now, "httpStatus": code})
                elif action == "finish":
                    log("operator-events.jsonl", {"event": "terminal", "t": now, "status": status, "flags": flags})
                    return 0 if status == "COMPLETED" else 1
                elif action.startswith("skip_"):
                    flags["skipped"].append(action[5:])
                    log(
                        "operator-events.jsonl",
                        {"event": "not_exercised", "t": now, "step": action[5:], "applied": applied},
                    )
                elif action in ("join", "rejoin", "leave"):
                    code, body = member_change("remove" if action == "leave" else "add")
                    log(
                        "operator-events.jsonl",
                        {"event": action, "t": now, "applied": applied, "httpStatus": code, "reply": body},
                    )
                    if code == 200:
                        flags[{"join": "joined", "rejoin": "rejoinedAt", "leave": "left"}[action]] = now
                        if action == "rejoin":
                            flags["jBase"] = snap.get("workers", {}).get(JOINER, 0)
                elif action == "fault_quang":
                    flags["killedAt"] = now
                    flags["qBase"] = snap.get("workers", {}).get(QUANG, 0)
                    with (HELPERS / "worker_proc.py").open() as script:
                        out = ssh(QUANG_HOST, "python3 - kill", stdin=script)
                    log(
                        "operator-events.jsonl",
                        {
                            "event": "injected_quang",
                            "t": now,
                            "applied": applied,
                            "activeLease": snap["active"][QUANG],
                            "receipt": json.loads(out.strip().splitlines()[-1]),
                        },
                    )
                elif action == "fault_win":
                    flags["stoppedAt"] = now  # set first: a failure after the stop must still lead to the relaunch
                    flags["winBase"] = snap.get("workers", {}).get(WIN, 0)
                    receipt = json.loads(powershell(HELPERS / "fault-windows.ps1").strip().splitlines()[-1])
                    log(
                        "operator-events.jsonl",
                        {
                            "event": "injected_win",
                            "t": now,
                            "applied": applied,
                            "activeLease": snap["active"][WIN],
                            "receipt": receipt,
                        },
                    )
                elif action == "relaunch":
                    # The launch control keeps its session open after the app starts; it is not waited for.
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(ROOT / ".scratch/windows-system-finish/run-ps.py"),
                            str(HELPERS / "launch-c9.ps1"),
                        ],
                        stdout=open(HELPERS / "relaunch.log", "a"),
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    flags["relaunched"] = now
                    log(
                        "operator-events.jsonl",
                        {"event": "relaunch_requested", "t": now, "outageSeconds": now - flags["stoppedAt"]},
                    )
                elif action == "contribution":
                    code, devices = call("GET", "/api/v1/devices")
                    device = next(d for d in devices if d["workerId"] == WIN)
                    if device["connectionStatus"] == "ONLINE" and device["contributionEnabled"]:
                        flags["contributionOn"] = now
                    elif device["connectionStatus"] == "ONLINE":
                        code, _ = call(
                            "POST",
                            f"/api/v1/devices/{device['deviceId']}/contribution",
                            {"enabled": True, "bootId": device["bootId"]},
                        )
                        log(
                            "operator-events.jsonl",
                            {
                                "event": "restart_contribution_on",
                                "t": now,
                                "httpStatus": code,
                                "bootId": device["bootId"],
                            },
                        )
                        if code == 200:
                            flags["contributionOn"] = now
                elif action.startswith("verdict_"):
                    who = action[8:]
                    status_of = {"quang": quang_status, "rejoin": rejoin_status, "win": win_status}[who]
                    flags[who + "Verdict"] = status_of(flags, snap, now)
                    log(
                        "operator-events.jsonl",
                        {
                            "event": "restart_verdict",
                            "t": now,
                            "worker": who,
                            "verdict": flags[who + "Verdict"],
                            "applied": applied,
                            "restarts": snap.get("restarts"),
                            "results": snap.get("workers"),
                            "note": "failed = STOP RULE: no automatic restart within the deadline; the run goes on, no manual fix",
                        },
                    )
        except Exception as error:  # one failed read or action is retried on the next round
            failures += 1
            log(
                "operator-events.jsonl",
                {"event": "monitor_error", "t": time.time(), "error": str(error)[:300], "consecutive": failures},
            )
        time.sleep(10)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
