"""E4 configuration on one RTX 5070 Ti: recovery point every generation (run 5f0c79f0, 25/11) against every 10
generations (run 6131a0ad, 26/11). Same model (E4 segment-2 start), data, alpha, sigma, 384 tokens, 32 candidates.
Writes data/speed-backup10.json; prints a per-generation table.

    python3 src/speed_backup10.py
"""

import collections
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path.home() / ".local/share/heteroes-worker/agent-state/runs"
OLD, NEW = "5f0c79f03a834cdfa7bc8f60ed5d5bad", "6131a0ade3834556b9051407c0516bd3"


def generations(run_id):
    first = collections.defaultdict(dict)
    for line in (RUNS / run_id / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if "generation" in e:
            first[e["generation"]].setdefault(e["event"], e["t"])
    rows = []
    for g in sorted(first):
        a, b = first[g], first.get(g + 1, {})
        needed = ("generation_open", "generation_complete", "update_applied", "generation_done")
        if "generation_open" not in b or not all(k in a for k in needed) or "validation_completed" in a:
            continue
        rows.append({
            "generation": g,
            "total": round(b["generation_open"] - a["generation_open"], 2),
            "scoring": round(a["generation_complete"] - a["generation_open"], 2),
            "update": round(a["update_applied"] - a["generation_complete"], 2),
            "publish": round(a["generation_done"] - a["update_applied"], 2),
            "tail": round(b["generation_open"] - a["generation_done"], 2),
        })
    return rows


def summary(rows):
    keys = ("total", "scoring", "update", "publish", "tail")
    return {
        "generations": len(rows),
        "median": {k: round(statistics.median(r[k] for r in rows), 1) for k in keys},
        "mean": {k: round(statistics.mean(r[k] for r in rows), 1) for k in keys},
    }


out = {}
for label, run in (("everyGeneration", OLD), ("every10", NEW)):
    rows = generations(run)
    out[label] = {"run": run, "rows": rows, **summary(rows)}
    print(label, run[:8], json.dumps({k: out[label][k] for k in ("generations", "median", "mean")}, ensure_ascii=False))
    for r in rows:
        print("   ", r)
(ROOT / "data" / "speed-backup10.json").write_text(json.dumps(out, indent=1) + "\n")
print("wrote data/speed-backup10.json")
