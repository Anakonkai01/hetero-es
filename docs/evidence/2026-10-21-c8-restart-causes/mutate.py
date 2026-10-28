"""Mutation check of the c8 restart fixes on a scratch copy (the repository is never modified): python mutate.py <scratch>."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path.home() / "projects/heteroes"
WORK = Path(sys.argv[1])
SUP = "runtime/src/heteroes/product/run_supervisor.py"
QUAL = "backend/devices.py"
SCHED = "backend/agent_scheduling.py"
APP = "desktop/worker/electron/service.cjs"
MUTANTS = [
    (
        QUAL,
        'if d["boot_id"] == body.bootId and body.selfTest.model_dump() == old:',
        "if body.selfTest.model_dump() == old:",
    ),
    (QUAL, 'if d["boot_id"] == body.bootId and body.selfTest.model_dump() == old:', 'if d["boot_id"] == body.bootId:'),
    (QUAL, '                return {"updated": False}\n', "                pass\n"),
    (SCHED, '        left -= set(self.intended_members(db, row["run_id"], initial))\n', ""),
    (SCHED, 'initial = json.loads(experiment[0])["workerIds"] if experiment else []', "initial = []"),
    (SUP, "                if self.deferred.get(key) != reason:", "                if True:"),
    (SUP, "                if self.deferred.get(key) != reason:", "                if key not in self.deferred:"),
    (SUP, "                    self.deferred[key] = reason\n", ""),
    (SUP, '"httpStatus": error.code if isinstance(error, urllib.error.HTTPError) else None,', '"httpStatus": None,'),
    (SUP, "            self.deferred.pop(key, None)\n", ""),
    (
        APP,
        "      this.recordAgentFailure(error, failed);\n      throw error;\n    }\n  }\n  async pair",
        "      throw error;\n    }\n  }\n  async pair",
    ),
]
PY = str(Path.home() / "miniforge3/envs/heteroes-match/bin/python")
results = []
for i, (path, old, new) in enumerate(MUTANTS):
    if WORK.exists():
        shutil.rmtree(WORK)
    for d in ("runtime", "backend", "desktop/worker"):
        ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", "node_modules", "dist", "build")
        shutil.copytree(REPO / d, WORK / d, ignore=ignore)
    f = WORK / path
    text = f.read_text()
    assert text.count(old) == 1, (i, old)
    f.write_text(text.replace(old, new))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
    if path.startswith("backend/"):
        cmd = [str(REPO / ".venv-backend/bin/python"), "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
        cmd += ["backend/tests/test_devices.py", "backend/tests/test_membership.py"]
        cwd = WORK
    elif path == APP:
        cmd, cwd = ["node", "--test", "tests/compute.test.cjs"], WORK / "desktop/worker"
    else:
        env["PYTHONPATH"] = "src"
        cmd = [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests/ledger/test_run_supervisor.py"]
        cwd = WORK / "runtime"
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    killed = r.returncode != 0
    results.append(killed)
    print(
        f"mutant {i + 1:2d} {'KILLED' if killed else 'SURVIVED'}  {path.split('/')[-1]}: {old.strip()[:70]!r}",
        flush=True,
    )
print(f"{sum(results)}/{len(results)} killed")
