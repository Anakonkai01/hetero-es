#!/usr/bin/env python3
"""Export the update records of a run (from its ledger) and the hashes of its kept checkpoints into one small JSON file that a replaying machine can read.
    export_records.py --run-dir <run> --experiment-id lrtA --ckpt-dir <dir with g<NNN>-<sha>.bin> --output records-lrtA.json
Run it where the ledger is (the 5070 Ti) with the heteroes-match python and PYTHONPATH=src."""
import argparse
import json
import sys
from pathlib import Path

from heteroes.ledger import Ledger

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run-dir", required=True)
parser.add_argument("--experiment-id", required=True)
parser.add_argument("--ckpt-dir", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
if Path(args.output).exists():
    sys.exit(f"{args.output} exists; evidence is never overwritten")
ledger = Ledger(Path(args.run_dir) / "coordinator/ledger.sqlite", enforce_chain=True)
checkpoints = {}
for path in sorted(Path(args.ckpt_dir).glob("g*-*.bin")):
    generation, sha = path.stem[1:].split("-")
    checkpoints[int(generation)] = sha
last = max(checkpoints)
records = []
for generation in range(last):
    stored = ledger.get_update(args.experiment_id, generation)
    if stored is None:
        sys.exit(f"no update record for generation {generation}")
    records.append({"generation": generation, "record_json": stored.record.to_json(), "record_hash": stored.record_hash, "child_weights_sha256": stored.child_weights_sha256})
Path(args.output).write_text(json.dumps({"experiment_id": args.experiment_id, "checkpoints": checkpoints, "records": records}) + "\n")
print(f"wrote {args.output}: {len(records)} records, {len(checkpoints)} checkpoint hashes")
