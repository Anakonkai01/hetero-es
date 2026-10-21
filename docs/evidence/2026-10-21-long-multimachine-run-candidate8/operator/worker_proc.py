"""Operator failure injection on a Linux machine: find the HeteroES compute worker (`scripts/run_worker.py`) and kill or
freeze that ONE process. The device agent and everything else stay untouched. A process is addressed by pid AND start
time, so a reused pid is never signalled. The process scan reads /proc and matches argv exactly (no `pkill -f`).

    python3 worker_proc.py list
    python3 worker_proc.py kill                  # SIGKILL the single worker; prints a receipt
    python3 worker_proc.py stop [--resume-after N]  # SIGSTOP; a detached timer sends SIGCONT after N seconds at the latest
    python3 worker_proc.py cont --pid P --start S [--after N]

Run remotely with `ssh host python3 - kill < worker_proc.py`.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def read_proc(pid):
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        argv = [a.decode(errors="replace") for a in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if a]
    except OSError:
        return None
    rest = raw[raw.rindex(")") + 2 :].split()
    return {"pid": pid, "state": rest[0], "ppid": int(rest[1]), "start": int(rest[19]), "argv": argv}


def workers():
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        info = read_proc(int(entry))
        if info and len(info["argv"]) > 1 and info["argv"][1].endswith("run_worker.py"):
            found.append(info)
    return found


def describe(info):
    parent = read_proc(info["ppid"])
    return {
        "pid": info["pid"],
        "start": info["start"],
        "state": info["state"],
        "ppid": info["ppid"],
        "parent": [Path(a).name[:60] for a in (parent or {}).get("argv", [])[:2]],
        "argv": [Path(a).name if a.startswith("/") else a for a in info["argv"][:3]],
    }


def single():
    found = workers()
    if len(found) != 1:
        raise SystemExit(f"expected exactly one run_worker.py process, found {len(found)}")
    return found[0]


def checked(pid, start):
    info = read_proc(pid)
    if not info or info["start"] != start:
        raise SystemExit("that worker process is gone or its pid was reused")
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "kill", "stop", "cont"))
    parser.add_argument("--pid", type=int)
    parser.add_argument("--start", type=int)
    parser.add_argument("--resume-after", type=int, default=300)
    parser.add_argument("--after", type=int, default=0)
    a = parser.parse_args()
    if a.action == "list":
        print(json.dumps([describe(i) for i in workers()]))
        return
    if a.action == "cont":
        time.sleep(a.after)
        info = checked(a.pid, a.start)
        os.kill(info["pid"], signal.SIGCONT)
        time.sleep(1)
        print(json.dumps({"event": "sigcont", "t": time.time(), "after": describe(read_proc(a.pid))}))
        return
    info = single() if a.pid is None else checked(a.pid, a.start)
    before = describe(info)
    parent = info["ppid"]
    t = time.time()
    if a.action == "kill":
        os.kill(info["pid"], signal.SIGKILL)
        time.sleep(2)
        gone = read_proc(info["pid"]) is None
        print(json.dumps({"event": "worker_kill", "t": t, "worker": before, "gone": gone,
                          "parentAlive": read_proc(parent) is not None}))
        raise SystemExit(0 if gone else 1)
    os.kill(info["pid"], signal.SIGSTOP)
    time.sleep(1)
    now = read_proc(info["pid"])
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "cont", "--pid", str(info["pid"]), "--start",
         str(info["start"]), "--after", str(a.resume_after)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    print(json.dumps({"event": "worker_stop", "t": t, "worker": before, "stopped": bool(now and now["state"] == "T"),
                      "resumeAfterAtLatest": a.resume_after}))
    raise SystemExit(0 if now and now["state"] == "T" else 1)


if __name__ == "__main__":
    main()
