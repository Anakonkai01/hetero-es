#!/usr/bin/env python3
"""Export a completed local experiment for historical cloud import."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteroes.product.files import read_json
from heteroes.product.recovery import capture_point, verify_point
from heteroes.product.remote import alive


def export(root):
    root = Path(root)
    if read_json(root / "state.json", {}).get("status") != "COMPLETED" or alive(read_json(root / "process.json")):
        raise RuntimeError("Only a completed, stopped coordinator may be exported")
    states = read_json(root / "state.json")["workerStates"]
    if set(states) != set(read_json(root / "config.json")["workerIds"]):
        raise RuntimeError("Missing selected worker shutdown evidence")
    for state in states.values():
        if state.get("alive") or not state.get("confirmed"):
            raise RuntimeError("Confirm all selected workers stopped before exporting")
    with sqlite3.connect(f"file:{root / 'ledger.sqlite'}?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT g.generation,g.parent_weights_sha256,u.child_weights_sha256 FROM generation g JOIN generation_update u USING(experiment_id,generation) WHERE applied_at IS NOT NULL ORDER BY g.generation DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise ValueError("No published generation")
    starts = [
        json.loads(line)
        for line in (root / "events.jsonl").read_text().splitlines()
        if json.loads(line).get("event") == "managed_start"
    ]
    if not starts or not starts[-1].get("recipe"):
        raise ValueError("Pinned recipe identity unavailable")
    point = capture_point(
        root,
        {"generation": row[0], "parent_sha256": row[1], "child_sha256": row[2]},
        starts[-1]["recipe"],
        {"interval": 1, "retain": 3},
        final=True,
        identity={k: starts[-1][k] for k in ("code", "environment") if k in starts[-1]},
    )
    manifest = verify_point(point)
    return {
        "pointDirectory": str(point),
        "runId": manifest["runId"],
        "childWeightsSha256": manifest["childWeightsSha256"],
        "verified": True,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-directory", required=True, type=Path)
    a = p.parse_args()
    print(json.dumps(export(a.run_directory), indent=2))
