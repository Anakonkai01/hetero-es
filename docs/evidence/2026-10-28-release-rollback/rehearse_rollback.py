#!/usr/bin/env python3
"""Rollback rehearsal for a lab deploy: new code writes a lab database, the old (deployed) code reopens and changes it,
the new code reopens it again. CPU only, temporary state, no ports, never the live lab or its configuration.

    python3 rehearse_rollback.py --repo <checkout> --old 82c37fca --new HEAD --python <backend python> --out <dir>

Each phase runs in its own process with PYTHONPATH set to a `git archive` of that commit (backend, scripts, runtime/src),
opens the same SQLite file through `backend.app.create_app`, and reads the lab through its own HTTP routes (TestClient).
Pass: every phase sees the same devices and experiments, and the old code's write is visible to the new code.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

DRIVER = r"""
import json, sys
from pathlib import Path
sys.path[:0] = [sys.argv[1], sys.argv[1] + "/runtime/src"]
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.devices import AgentRuntime
from backend.local_storage import LocalBackend
import importlib.util
spec = importlib.util.spec_from_file_location("lab", sys.argv[1] + "/scripts/serve-test-lab.py")
lab = importlib.util.module_from_spec(spec); spec.loader.exec_module(lab)
state, phase = Path(sys.argv[2]), sys.argv[3]
app = create_app(state / "product.sqlite", lab.USERS, AgentRuntime(LocalBackend(state / "objects", state / "storage-key",
                 "http://127.0.0.1:9")), dispatch=False)
if phase == "seed":
    lab.pair_devices(app)
    lab.load_run(app.state.store, json.loads(Path(sys.argv[4]).read_text()))
c = TestClient(app)
token = c.post("/api/v1/auth/login", json={"username": "admin", "password": lab.USERS["admin"]}).json()["accessToken"]
h = {"Authorization": "Bearer " + token, "X-Workspace-Id": "lab"}
if phase == "old":  # the rolled-back code must still be able to write: rename a device
    devices = c.get("/api/v1/devices", headers=h).json()
    first = (devices.get("items") if isinstance(devices, dict) else devices)[0]
    r = c.patch(f"/api/v1/devices/{first['deviceId']}", headers=h, json={"displayName": "renamed-by-old-code"})
    print(json.dumps({"write": r.status_code}), file=sys.stderr)
def ids(path, key):
    body = c.get(path, headers=h).json()
    items = body.get("items", body) if isinstance(body, dict) else body
    return sorted((item.get(key), item.get("displayName") or item.get("name")) for item in items)
print(json.dumps({"health": c.get("/api/v1/health").status_code,
                  "devices": ids("/api/v1/devices", "deviceId"),
                  "experiments": ids("/api/v1/experiments", "experimentId")}))
"""


def unpack(repo, rev, into):
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", rev, "backend", "scripts", "runtime/src"], capture_output=True, check=True
    ).stdout
    into.mkdir(parents=True)
    with tempfile.TemporaryFile() as f:
        f.write(archive)
        f.seek(0)
        tarfile.open(fileobj=f).extractall(into, filter="data")
    return into


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--old", required=True)
    p.add_argument("--new", default="HEAD")
    p.add_argument("--python", required=True)
    p.add_argument("--seed-run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        trees = {name: unpack(a.repo, rev, work / name) for name, rev in (("old", a.old), ("new", a.new))}
        state = work / "state"
        state.mkdir()
        seen = {}
        for phase, tree in (("seed", "new"), ("old", "old"), ("new", "new")):
            done = subprocess.run(
                [a.python, "-I", "-c", DRIVER, str(trees[tree]), str(state), phase, str(a.seed_run.resolve())],
                capture_output=True, text=True, env={"CUDA_VISIBLE_DEVICES": "", "PATH": "/usr/bin:/bin"},
            )
            (a.out / f"{phase}.stderr.txt").write_text(done.stderr)
            if done.returncode:
                raise SystemExit(f"phase {phase} failed; see {a.out}/{phase}.stderr.txt")
            seen[phase] = json.loads(done.stdout.strip().splitlines()[-1])
    failures = []
    if any(view["health"] != 200 for view in seen.values()):
        failures.append("a phase did not answer health")
    if seen["seed"]["experiments"] != seen["old"]["experiments"] or seen["old"]["experiments"] != seen["new"]["experiments"]:
        failures.append("experiments differ between phases")
    if not seen["seed"]["experiments"] or not seen["seed"]["devices"]:
        failures.append("nothing was seeded, so the rehearsal proves nothing")
    if not any(name == "renamed-by-old-code" for _, name in seen["new"]["devices"]):
        failures.append("the old code's write is not visible to the new code")
    report = {"old": a.old, "new": a.new, "phases": seen, "failures": failures}
    (a.out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))
    print("ROLLBACK REHEARSAL " + ("FAILED" if failures else "OK"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
