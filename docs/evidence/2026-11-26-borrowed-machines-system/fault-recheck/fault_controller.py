"""Takes 5070ti-nhut away from a running run and gives it back, at generation boundaries seen in the coordinator's
events: crash (kill -9 of its worker service) at gen CRASH, graceful OFF at gen OFF, ON + re-add at gen ON."""
import json, subprocess, sys, time
from pathlib import Path
sys.path[:0] = [str(Path.home() / "projects/heteroes/runtime/src")]
from heteroes.sdk_lab import Lab

run_id, CRASH, OFF, ON = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
NHUT = "<nhut-ssh>"
log = Path.home() / f"heteroes-experiments/borrowed-20261126/fault-actions-{run_id[:8]}.jsonl"
events = Path.home() / f".local/share/heteroes-worker/agent-state/runs/{run_id}/events.jsonl"
lab = Lab.from_session()
nhut_id = next(d.worker_id for d in lab.devices() if d.name == "5070ti-nhut")


def note(action, **extra):
    row = {"t": time.time(), "action": action, **extra}
    log.open("a").write(json.dumps(row) + "\n")
    print(row, flush=True)


def ssh(cmd):
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", NHUT, "export PATH=$HOME/.local/bin:$PATH; " + cmd],
                       capture_output=True, text=True, timeout=300)
    return (r.stdout + r.stderr).strip()[-800:]


def generation():
    if not events.exists():
        return -1
    opened = [json.loads(l)["generation"] for l in events.read_text().splitlines() if "\"generation_open\"" in l]
    return max(opened) if opened else -1


done = set()
while True:
    g = generation()
    status = lab.run(run_id).status()
    if status in ("COMPLETED", "FAILED", "CANCELLED"):
        note("run_ended", status=status)
        break
    if g >= CRASH and "crash" not in done:
        note("crash_start", generation=g)
        note("crash", generation=g, out=ssh("systemctl --user kill -s KILL heteroes-worker; sleep 2; systemctl --user status heteroes-worker | head -3"))
        done.add("crash")
    if g >= OFF and "off" not in done:
        note("off", generation=g, out=ssh("heteroes-worker off"))
        done.add("off")
    if g >= ON and "on" not in done:
        note("on", generation=g, out=ssh("heteroes-worker on --keep-after-reboot"))
        time.sleep(20)
        try:
            r = lab.request("POST", f"/api/v1/experiments/{run_id}/workers", {"workerId": nhut_id, "action": "add"})
        except Exception as e:  # noqa: BLE001
            r = repr(e)
        note("re-add", generation=g, response=r)
        done.add("on")
    time.sleep(5)
