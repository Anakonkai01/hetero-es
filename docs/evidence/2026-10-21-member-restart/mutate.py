import shutil, subprocess, sys, os
from pathlib import Path
REPO = Path.home() / "projects/heteroes"
WORK = Path(sys.argv[1])
SUP = "runtime/src/heteroes/product/run_supervisor.py"
AG = "runtime/src/heteroes/product/agent.py"
LAB = "backend/agent_commands.py"
MUTANTS = [
    (SUP, 'launch = 0 if value.get("notStarted") else value.get("launch", 0) + 1', 'launch = value.get("launch", 0) + 1'),
    (SUP, 'value.get("launch", 0) + 1  # a never', 'value.get("launch", 0)  # a never'),
    (SUP, 'if not stopped or not value.get("confirmed") or worker_id in quarantined:', 'if not stopped or worker_id in quarantined:'),
    (SUP, 'if not stopped or not value.get("confirmed") or worker_id in quarantined:', 'if not stopped or not value.get("confirmed"):'),
    (SUP, '            if now < self.retry_at.get(key, 0):\n                continue\n', ''),
    (SUP, 'if launch >= MAX_LAUNCHES:', 'if launch > MAX_LAUNCHES:'),
    (SUP, '"runId": root.name + f"-r{recovery}", **launched(launch)},\n                )\n                write_json', '"runId": root.name + f"-r{recovery}"},\n                )\n                write_json'),
    (SUP, '            self._restart_members(root, self.state(root))\n', ''),
    (SUP, 'self._launch_worker(root, worker_id, result, recovery, launch)\n', 'self._launch_worker(root, worker_id, result, recovery, 0)\n'),
    (AG, '                if owned_state(read_json(old / "process.json"), (old / "launch-intent.json").exists()) is not False:', '                if owned_state(read_json(old / "process.json"), (old / "launch-intent.json").exists()) is True:'),
    (AG, '(f"r{recovery}-l{launch}" if launch else f"r{recovery}")', 'f"r{recovery}"'),
    (AG, '                **launched(ar.get("launch", 0)),\n', ''),
    (AG, 'continue  # the newest launch', 'pass  # the newest launch'),
    (AG, '                **launched(body.get("launch", 0)),\n', ''),
    (LAB, '                and p.get("launch", 0) == body.launch  # never', '                # never'),
    (LAB, 'f"worker:{row[\'id\']}:{did}:{body.recoveryIndex}{suffix}"', 'f"worker:{row[\'id\']}:{did}:{body.recoveryIndex}"'),
    (LAB, '"recoveryIndex": body.recoveryIndex, **launch},', '"recoveryIndex": body.recoveryIndex},'),
]
PY = str(Path.home() / "miniforge3/envs/heteroes-match/bin/python")
results = []
for i, (path, old, new) in enumerate(MUTANTS):
    if WORK.exists():
        shutil.rmtree(WORK)
    for d in ("runtime", "backend"):
        shutil.copytree(REPO / d, WORK / d, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    f = WORK / path
    text = f.read_text()
    assert text.count(old) == 1, (i, old)
    f.write_text(text.replace(old, new))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
    if path == LAB:
        cmd = [str(REPO / ".venv-backend/bin/python"), "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "backend/tests/test_devices.py", "backend/tests/test_membership.py"]
        cwd = WORK
    else:
        env["PYTHONPATH"] = "src"
        cmd = [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests/ledger/test_run_supervisor.py", "tests/ledger/test_device_agent.py", "tests/ledger/test_product_membership.py"]
        cwd = WORK / "runtime"
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    killed = r.returncode != 0
    results.append(killed)
    print(f"mutant {i+1:2d} {'KILLED' if killed else 'SURVIVED'}  {path.split('/')[-1]}: {old.strip()[:70]!r}", flush=True)
print(f"{sum(results)}/{len(results)} killed")
