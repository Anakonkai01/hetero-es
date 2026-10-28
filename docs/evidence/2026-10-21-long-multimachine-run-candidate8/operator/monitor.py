"""Detached operator monitor for the candidate8 final acceptance (runs on the 5070).

Every 10 s it reads the coordinator's ledger (snapshot.py over SSH, read-only) and the lab, and performs the declared
events once each, one after the previous one has recovered (or its deadline passed):

  1 JOIN the 1660S (g>=10)            4 kill -9 Quang's worker process (g>=32), the agent stays up
  2 hard-stop Thao's Windows app (g>=14), relaunch ~240 s later, contribution ON; the restart must come by itself
  3 LEAVE the 1660S (g>=28)           5 JOIN the 1660S again (g>=38)
                                      6 SIGSTOP the 5070 worker (g>=40) ~180 s, then SIGCONT (a stale result)

A restart that does not happen within 10 minutes is recorded as a stop-rule failure; the run itself goes on. An audit
mismatch or a quarantine requests PAUSE and stops the monitor. `decide` is pure so the event logic is tested without
machines.

    python3 monitor.py <experiment id>
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/pc5070ti/projects/heteroes")
EVIDENCE = ROOT / "docs/evidence/2026-10-21-long-multimachine-run-candidate8"
HELPERS = ROOT / ".scratch/r11-c8-run"
WORKSPACE = "bcbece5a24834ac28e358fc49db1343f"
THAO = "thao_nguyen@100.92.20.58"
QUANG_HOST = "quang@100.99.227.8"
JOINER = "cli-3e355c6e9e70"  # GTX 1660 SUPER
WIN = "desktop-9f9da13f0f82"  # Thao native Windows 3060
QUANG = "cli-894b5d440398"  # Quang WSL 3060
LOCAL = "desktop-906949218c43"  # 5070 Ti
WATCH = f"{WIN},{QUANG},{LOCAL},{JOINER}"
JOIN1_AT, WIN_AT, WIN_SKIP, OUTAGE = 10, 14, 24, 240
LEAVE_AT, QUANG_AT, QUANG_SKIP = 28, 32, 40
JOIN2_AT, JOIN2_SKIP, SIG_AT, SIG_SKIP = 38, 44, 40, 44
STOP_SECONDS, STOP_MAX, RESTART_DEADLINE = 180, 300, 600
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "PAUSED")


def restart_status(snap, worker, since, base, now):
    """A killed member must be started again by the system: a `worker_restarted` event after `since`, then new results."""
    restarted = any(e[0] == "worker_restarted" and e[1] == worker and e[3] >= since for e in snap.get("restarts", []))
    produced = snap.get("workers", {}).get(worker, 0) > base
    if restarted and produced:
        return "recovered"
    return "failed" if now - since >= RESTART_DEADLINE else "waiting"


def win_status(flags, snap, now):
    if "win" in flags.get("skipped", []):
        return "skipped"
    if not flags.get("stoppedAt"):
        return "open"
    if not flags.get("contributionOn"):  # the app never came back: nothing could be restarted
        relaunched = flags.get("relaunched")
        return "failed" if relaunched and now - relaunched >= RESTART_DEADLINE else "open"
    return restart_status(snap, WIN, flags["contributionOn"], flags["winBase"], now)


def quang_status(flags, snap, now):
    if "quang" in flags.get("skipped", []):
        return "skipped"
    if not flags.get("killedAt"):
        return "open"
    return restart_status(snap, QUANG, flags["killedAt"], flags["qBase"], now)


DONE = ("recovered", "failed", "skipped")


def decide(flags, snap, status, now):
    """The actions due now, given what was already done (`flags`), a ledger snapshot and the lab's status."""
    if (snap.get("audits", [0, 0])[1] or snap.get("quarantines")) and not flags.get("pauseRequested"):
        return ["pause"]
    if status in TERMINAL:
        return ["finish"]
    applied = snap.get("applied", 0)
    active = snap.get("active", {})
    skipped = flags.get("skipped", [])
    actions = []
    if applied >= JOIN1_AT and not flags.get("joined"):
        actions.append("join")
    # 2: Thao Windows, whole app
    if applied >= WIN_AT and not flags.get("stoppedAt") and active.get(WIN) and "win" not in skipped:
        actions.append("fault_win")
    elif applied >= WIN_SKIP and not flags.get("stoppedAt") and "win" not in skipped:
        actions.append("skip_win")
    if flags.get("stoppedAt") and not flags.get("relaunched") and now - flags["stoppedAt"] >= OUTAGE:
        actions.append("relaunch")
    if flags.get("relaunched") and not flags.get("contributionOn"):
        actions.append("contribution")
    if flags.get("stoppedAt") and not flags.get("winVerdict") and win_status(flags, snap, now) in ("recovered", "failed"):
        actions.append("verdict_win")
    win_done = win_status(flags, snap, now) in DONE
    # 3
    if applied >= LEAVE_AT and flags.get("joined") and not flags.get("left") and win_done:
        actions.append("leave")
    # 4: Quang, the worker process only
    if win_done and applied >= QUANG_AT and not flags.get("killedAt") and "quang" not in skipped:
        if active.get(QUANG):
            actions.append("fault_quang")
        elif applied >= QUANG_SKIP:
            actions.append("skip_quang")
    if flags.get("killedAt") and not flags.get("quangVerdict") and quang_status(flags, snap, now) in ("recovered", "failed"):
        actions.append("verdict_quang")
    quang_done = quang_status(flags, snap, now) in DONE
    # 5
    if flags.get("left") and not flags.get("joined2") and "join2" not in skipped and quang_done:
        if applied >= JOIN2_SKIP:
            actions.append("skip_join2")
        elif applied >= JOIN2_AT:
            actions.append("join2")
    # 6: the 5070 worker is frozen, then continued
    if quang_done and (flags.get("joined2") or "join2" in skipped) and applied >= SIG_AT and not flags.get("sigAt") \
            and "sig" not in skipped:
        if applied >= SIG_SKIP:
            actions.append("skip_sig")
        elif active.get(LOCAL):
            actions.append("sigstop")
    if flags.get("sigAt") and not flags.get("contAt"):
        waited = now - flags["sigAt"]
        expired = snap.get("expired", {}).get(LOCAL, 0) > flags.get("expBase", 0)
        if (waited >= STOP_SECONDS and expired) or waited >= STOP_MAX:
            actions.append("sigcont")
    return actions


def ssh(host, command, timeout=60, stdin=None):
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, command],
        capture_output=True, text=True, timeout=timeout, stdin=stdin,
    )
    if p.returncode:
        raise RuntimeError(f"SSH failed ({p.returncode}): " + (p.stderr or p.stdout)[:300])
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

    def member_change(action):
        return call("POST", f"/api/v1/experiments/{experiment}/workers", {"workerId": JOINER, "action": action})

    flags = {"skipped": []}
    failures = 0
    while True:
        try:
            snap = json.loads(ssh(THAO, f"python3 /tmp/heteroes-r11-c8/snapshot.py {experiment} {WATCH}"))
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
                    log("operator-events.jsonl", {"event": "STOP_AUDIT_PAUSE", "t": now, "httpStatus": code,
                                                  "audits": snap.get("audits"), "quarantines": snap.get("quarantines")})
                elif action == "finish":
                    log("operator-events.jsonl", {"event": "terminal", "t": now, "status": status, "flags": flags})
                    return 0 if status == "COMPLETED" else 1
                elif action.startswith("skip_"):
                    flags["skipped"].append(action[5:])
                    log("operator-events.jsonl", {"event": "not_exercised", "t": now, "step": action[5:], "applied": applied})
                elif action in ("join", "join2", "leave"):
                    code, body = member_change("remove" if action == "leave" else "add")
                    log("operator-events.jsonl", {"event": action, "t": now, "applied": applied, "httpStatus": code,
                                                  "reply": body})
                    if code == 200:
                        flags[{"join": "joined", "join2": "joined2", "leave": "left"}[action]] = now
                elif action == "fault_win":
                    flags["stoppedAt"] = now  # set first: a failure after the stop must still lead to the relaunch
                    flags["winBase"] = snap.get("workers", {}).get(WIN, 0)
                    receipt = json.loads(powershell(HELPERS / "fault-windows.ps1").strip().splitlines()[-1])
                    log("operator-events.jsonl", {"event": "injected_win", "t": now, "applied": applied,
                                                  "activeLease": snap["active"][WIN], "receipt": receipt})
                elif action == "relaunch":
                    # The launch control keeps its session open after the app starts; it is not waited for.
                    subprocess.Popen(
                        [sys.executable, str(ROOT / ".scratch/windows-system-finish/run-ps.py"),
                         str(HELPERS / "launch-c8.ps1")],
                        stdout=open(HELPERS / "relaunch.log", "a"), stderr=subprocess.STDOUT, start_new_session=True,
                    )
                    flags["relaunched"] = now
                    log("operator-events.jsonl", {"event": "relaunch_requested", "t": now,
                                                  "outageSeconds": now - flags["stoppedAt"]})
                elif action == "contribution":
                    code, devices = call("GET", "/api/v1/devices")
                    device = next(d for d in devices if d["workerId"] == WIN)
                    if device["connectionStatus"] == "ONLINE" and device["contributionEnabled"]:
                        flags["contributionOn"] = now
                    elif device["connectionStatus"] == "ONLINE":
                        code, _ = call("POST", f"/api/v1/devices/{device['deviceId']}/contribution",
                                       {"enabled": True, "bootId": device["bootId"]})
                        log("operator-events.jsonl", {"event": "restart_contribution_on", "t": now, "httpStatus": code})
                        if code == 200:
                            flags["contributionOn"] = now
                elif action == "fault_quang":
                    flags["killedAt"] = now
                    flags["qBase"] = snap.get("workers", {}).get(QUANG, 0)
                    with (HELPERS / "worker_proc.py").open() as script:
                        out = ssh(QUANG_HOST, "python3 - kill", stdin=script)
                    log("operator-events.jsonl", {"event": "injected_quang", "t": now, "applied": applied,
                                                  "activeLease": snap["active"][QUANG],
                                                  "receipt": json.loads(out.strip().splitlines()[-1])})
                elif action in ("verdict_win", "verdict_quang"):
                    who = action[8:]
                    flags[who + "Verdict"] = (win_status if who == "win" else quang_status)(flags, snap, now)
                    log("operator-events.jsonl", {
                        "event": "restart_verdict", "t": now, "worker": who, "verdict": flags[who + "Verdict"],
                        "applied": applied, "restarts": snap.get("restarts"), "results": snap.get("workers"),
                        "note": "failed = STOP RULE: no automatic restart within the deadline; the run goes on, no manual fix",
                    })
                elif action == "sigstop":
                    flags["sigAt"] = now
                    flags["expBase"] = snap.get("expired", {}).get(LOCAL, 0)
                    out = subprocess.run(
                        [sys.executable, str(HELPERS / "worker_proc.py"), "stop", "--resume-after", str(STOP_MAX + 30)],
                        capture_output=True, text=True, timeout=60)
                    receipt = json.loads(out.stdout.strip().splitlines()[-1])
                    flags["sigWorker"] = receipt["worker"]
                    log("operator-events.jsonl", {"event": "injected_sigstop", "t": now, "applied": applied,
                                                  "activeLease": snap["active"][LOCAL], "receipt": receipt})
                elif action == "sigcont":
                    worker = flags["sigWorker"]
                    out = subprocess.run(
                        [sys.executable, str(HELPERS / "worker_proc.py"), "cont", "--pid", str(worker["pid"]),
                         "--start", str(worker["start"])], capture_output=True, text=True, timeout=60)
                    flags["contAt"] = now
                    log("operator-events.jsonl", {"event": "sigcont", "t": now, "applied": applied,
                                                  "stoppedSeconds": now - flags["sigAt"],
                                                  "expiriesDuringStop": snap.get("expired", {}).get(LOCAL, 0) - flags["expBase"],
                                                  "receipt": out.stdout.strip()[-400:]})
        except Exception as error:  # one failed read or action is retried on the next round
            failures += 1
            log("operator-events.jsonl", {"event": "monitor_error", "t": time.time(), "error": str(error)[:300],
                                          "consecutive": failures})
        time.sleep(10)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
