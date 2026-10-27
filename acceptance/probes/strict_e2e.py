#!/usr/bin/env python3
"""
End-to-end strict run on two different GPUs: a CPU coordinator on this machine, a worker on the local RTX 5070 Ti and a
worker on Thảo's RTX 3060 (WSL2), all with Recipe v3 `strict_b22_v1` over the trained Qwen checkpoint.

The standalone coordinator (`python -m heteroes.v3 serve`) and workers (`... worker`) are the product's own processes;
the remote worker runs `git archive HEAD runtime/src` staged on the remote host. The shared run secret goes to the remote
over SSH standard input, never on a command line or in a file. The lab and its device states are not used.

Pass ("E2E OK") requires: every generation completed; both workers committed results; audits re-ran candidates on the
other worker and every completed audit matched (same texts across the two GPU architectures); the stored texts re-score
to the committed rewards; and the recorded updates, replayed on a fresh CPU model, give every published child hash.

    python3 acceptance/probes/strict_e2e.py --out .scratch/e2e-01 --generations 4
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import shlex
import sqlite3
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from acceptance.hosts import LOCAL, SSH, WSL  # noqa: E402

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--generations", type=int, default=4)
p.add_argument("--population", type=int, default=8)
p.add_argument("--audit-rate", type=float, default=0.5)
p.add_argument("--host", default="100.110.165.40", help="this machine's address reachable from the remote worker")
p.add_argument("--port", type=int, default=18765)
p.add_argument("--timeout-seconds", type=float, default=1800)
a = p.parse_args()
if a.out.exists():
    p.error("--out must be a fresh directory")
a.out.mkdir(parents=True)
token = secrets.token_hex(32)
env = {**os.environ, "HETEROES_TOKEN": token, "PYTHONPATH": str(REPO / "runtime/src")}
env.pop("HETEROES_GPU_ACCEPTANCE", None)  # the strict recipe is the opt-in of a managed worker

spec = {
    "model": {"path": f"{LOCAL.models}/qwen", "id": "Qwen/Qwen2.5-0.5B-Instruct"},
    "data": {"path": str(REPO / "acceptance/e2e/arith96.jsonl"), "promptField": "question"}
    | {"batchSize": 16, "batchSeed": 11, "splitSeed": 42},
    "weightSpace": {"kind": "subset", "include": [r"layers\.2[0-3]\."]},
    "sigma": {"kind": "constant", "initial": 0.001, "minimum": 0.001},
    "antithetic": True,
    "maxNewTokens": 32,
    "systemPrompt": "Answer with the number only.",
    "evalDtype": "float16",
    "decoder": "strict_b22_v1",
    "evalChunk": 16,
    "population": a.population,
    "generations": a.generations,
    "alpha": 0.001,
    "coefficientRule": "zscore@1",
    "scorer": {"kind": "declarative", "name": "last-integer", "version": 1, "codeSha256": None, "config": {}},
    "auditRate": a.audit_rate,
}
(a.out / "spec.json").write_text(json.dumps(spec, indent=1) + "\n")
run_dir = a.out / "coordinator"
url = f"http://{a.host}:{a.port}"
logs = {name: (a.out / f"{name}.log").open("w") for name in ("coordinator", "worker-local", "worker-remote")}
command = [LOCAL.runtime_python, "-m", "heteroes.v3", "serve", str(a.out / "spec.json"), "--out", str(run_dir)]
command += ["--host", a.host, "--port", str(a.port), "--device", "cpu", "--worker-ids", "local-5070ti,thao-3060"]
command += ["--timeout-seconds", str(a.timeout_seconds)]
coordinator = subprocess.Popen(command, env=env, stdout=logs["coordinator"], stderr=subprocess.STDOUT)
deadline = time.monotonic() + 600
while not (run_dir / "server.json").exists():
    if coordinator.poll() is not None or time.monotonic() > deadline:
        raise SystemExit(f"the coordinator did not start; see {a.out / 'coordinator.log'}")
    time.sleep(1)
server = json.loads((run_dir / "server.json").read_text())

local = subprocess.Popen(
    [LOCAL.runtime_python, "-m", "heteroes.v3", "worker", "--coordinator", url, "--model-path", f"{LOCAL.models}/qwen"]
    + ["--worker-id", "local-5070ti", "--out", str(a.out / "worker-local"), "--device", "cuda"]
    + ["--recipe-hash", server["recipeHash"]],
    env=env,
    stdout=logs["worker-local"],
    stderr=subprocess.STDOUT,
)

# the remote worker: stage this commit's runtime source, read the secret from stdin, run the product worker
tree = subprocess.run(
    ["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO, capture_output=True, text=True
).stdout.strip()
remote_root = f"/tmp/heteroes-e2e-{tree}-{time.strftime('%H%M%S')}"
archive = subprocess.run(
    ["git", "archive", "--format=tar", "HEAD", "runtime/src"], cwd=REPO, capture_output=True, check=True
)
subprocess.run([*SSH, f"mkdir -p {remote_root} && tar -xf - -C {remote_root}"], input=archive.stdout, check=True)
worker = shlex.join(
    [WSL.runtime_python, "-m", "heteroes.v3", "worker", "--coordinator", url, "--model-path", f"{WSL.models}/qwen"]
    + ["--worker-id", "thao-3060", "--out", f"{remote_root}/worker", "--device", "cuda"]
    + ["--recipe-hash", server["recipeHash"]]
)
variables = " ".join(
    f"{k}={shlex.quote(v)}" for k, v in {**WSL.env, "PYTHONPATH": f"{remote_root}/runtime/src"}.items()
)
remote = subprocess.Popen(
    [*SSH, f"read -r HETEROES_TOKEN && export HETEROES_TOKEN && cd {remote_root} && {variables} exec {worker}"],
    stdin=subprocess.PIPE,
    stdout=logs["worker-remote"],
    stderr=subprocess.STDOUT,
)
remote.stdin.write((token + "\n").encode())
remote.stdin.close()

status = coordinator.wait()
for process in (local, remote):
    try:
        process.wait(120)
    except subprocess.TimeoutExpired:
        process.terminate()
subprocess.run(
    [*SSH, f"cd {remote_root} && tar -czf - worker/events.jsonl worker/identity.json"],
    stdout=(a.out / "worker-remote.tar.gz").open("wb"),
)
report = {"coordinatorExit": status, "recipeHash": server["recipeHash"], "failures": []}
if status != 0:
    report["failures"].append(f"coordinator exited with {status}")
else:
    sys.path.insert(0, str(REPO / "runtime/src"))
    from heteroes.es.update import apply_coefficients_
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.ledger import Ledger
    from heteroes.v3 import data as v3data
    from heteroes.v3.model import file_manifest, load, trainable_schema
    from heteroes.v3.scoring import score

    recipe = json.loads((run_dir / "recipe.json").read_text())
    plan = json.loads((run_dir / "plan.json").read_text())
    dataset = json.loads((run_dir / "dataset.json").read_text())
    summaries = json.loads((run_dir / "summaries.json").read_text())
    report["generations"] = len(summaries)
    report["audits"] = [row["audits"] for row in summaries]
    model, _ = load(spec["model"]["path"], file_manifest(spec["model"]["path"]))
    schema = trainable_schema(model, recipe["weightSpace"])
    with sqlite3.connect(run_dir / "ledger.sqlite") as db:
        workers = dict(db.execute(
            "SELECT a.worker_id, COUNT(*) FROM result r JOIN attempt a ON a.candidate_id=r.candidate_id "
            "AND a.attempt_number=r.attempt_number GROUP BY a.worker_id"
        ).fetchall())  # fmt: skip
        audits = db.execute(
            "SELECT u.worker_id, a.worker_id, u.matched FROM audit u JOIN result r USING(candidate_id) JOIN attempt a "
            "ON a.candidate_id=r.candidate_id AND a.attempt_number=r.attempt_number"
        ).fetchall()
    report["resultsByWorker"] = workers
    report["auditPairs"] = [list(row) for row in audits]
    with Ledger(run_dir / "ledger.sqlite") as ledger:
        children = []
        for generation in range(plan["generations"]):
            rows = v3data.batch(dataset, generation, recipe["data"]["batch"]["size"], recipe["data"]["batch"]["seed"])
            for candidate in ledger.list_candidates("local", generation):
                _, texts = ledger.get_completions(candidate.descriptor.candidate_id)
                if candidate.result.reward != score(plan["scorer"], texts, rows["rows"])[0]:
                    report["failures"].append(f"g{generation}: stored texts do not re-score to the committed reward")
            stored = ledger.get_update("local", generation)
            seeds, coefficients = stored.record.update_inputs()
            apply_coefficients_(
                model, schema, seeds, coefficients, stored.record.alpha, recipe["noise"]["chunkElements"],
                engine=recipe["noise"]["engine"],
            )  # fmt: skip
            children.append(stored.child_weights_sha256)
            if model_weights_sha256(model, schema) != stored.child_weights_sha256:
                report["failures"].append(f"g{generation}: replayed child differs from the published hash")
    report["children"] = children
    if len(summaries) != a.generations:
        report["failures"].append("not every generation completed")
    if set(workers) != {"local-5070ti", "thao-3060"}:
        report["failures"].append(f"results came from {sorted(workers)}, not from both GPUs")
    if not audits or any(auditor == original for auditor, original, _ in audits):
        report["failures"].append("no cross-worker audit ran")
    if any(matched != 1 for _, _, matched in audits):
        report["failures"].append("an audit text mismatch between the two GPUs")
(a.out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps(report, indent=1))
if report["failures"]:
    raise SystemExit(1)
print("E2E OK")
