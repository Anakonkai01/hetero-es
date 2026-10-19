#!/usr/bin/env python3
"""
C4, replay measured for real (experiment code). On THIS machine: load the pinned model (the base weights), then apply the recorded update of generation 0, 1, 2, ...
(`apply_coefficients_cuda_` with the seeds, coefficients and alpha of each record: no weights are transferred) and check the SHA-256 of all weights against the hash that the
other machine stored for the same generation (the kept checkpoints, every `--check-every` generations, and the child hash in the ledger for every generation with `--check-all`).
It reports the seconds of each update (CUDA synchronized, without the hash) and every comparison. Usage on the replaying machine:
    PYTHONPATH=src python replay_probe.py --records records-lrtA.json --model-path <snapshot> --output replay-<machine>-lrtA.json [--generations 100]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import torch

from heteroes.es.cuda_ops import apply_coefficients_cuda_
from heteroes.eval.candidate import model_weights_sha256
from heteroes.generation_record import GenerationRecord
from heteroes.model.loading import load_pinned_model

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--records", required=True)
parser.add_argument("--model-path", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--generations", type=int, default=None)
parser.add_argument("--check-every", type=int, default=5)
parser.add_argument("--check-all", action="store_true", help="also compare the child hash of the ledger after every generation (a SHA-256 of 1 GB each: slower)")
args = parser.parse_args()
if Path(args.output).exists():
    sys.exit(f"{args.output} exists; evidence is never overwritten")
data = json.loads(Path(args.records).read_text())
records = data["records"][: args.generations]
checkpoints = {int(g): sha for g, sha in data["checkpoints"].items()}
loaded = load_pinned_model(args.model_path, "cuda")
model, schema = loaded.model, loaded.schema
base = model_weights_sha256(model, schema)
if base != checkpoints[0]:
    sys.exit(f"the base weights here have the hash {base}, the run started from {checkpoints[0]}")
device_name = torch.cuda.get_device_name()
result = {"machine_gpu": device_name, "torch": torch.__version__, "experiment_id": data["experiment_id"], "base_sha256": base, "generations": [], "checks": []}
print(f"{device_name}: replaying {len(records)} generations of {data['experiment_id']}", flush=True)
for entry in records:
    generation = entry["generation"]
    record = GenerationRecord.from_json(entry["record_json"])
    if record.hash != entry["record_hash"]:
        sys.exit(f"the record of generation {generation} does not match its hash")
    torch.cuda.synchronize()
    started = time.perf_counter()
    apply_coefficients_cuda_(model, schema, list(record.seeds), list(record.coefficients), record.alpha)
    torch.cuda.synchronize()
    seconds = time.perf_counter() - started
    result["generations"].append({"generation": generation, "candidates": len(record.seeds), "apply_seconds": seconds, "record_bytes": len(entry["record_json"])})
    after = generation + 1
    expected = [("checkpoint", checkpoints[after])] if after in checkpoints and after % args.check_every == 0 else []
    if args.check_all and entry["child_weights_sha256"]:
        expected.append(("ledger_child", entry["child_weights_sha256"]))
    if expected:
        actual = model_weights_sha256(model, schema)
        for kind, sha in expected:
            result["checks"].append({"after_generation": generation, "kind": kind, "expected": sha, "actual": actual, "match": actual == sha})
            print(f"  after generation {generation} ({kind}): {'MATCH' if actual == sha else 'MISMATCH'}   last update {seconds:.2f} s", flush=True)
result["all_match"] = all(c["match"] for c in result["checks"])
Path(args.output).write_text(json.dumps(result, indent=1) + "\n")
times = [g["apply_seconds"] for g in result["generations"]]
print(f"done: {len(times)} updates, median {sorted(times)[len(times) // 2]:.2f} s, all hashes match: {result['all_match']}", flush=True)
