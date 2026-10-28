"""Print the numbers of the README from the raw files of the physical two-machine runs (run: python summarize.py).
Reads this folder (B3 greedy) and ../2026-10-06-g3-two-machines-cable-wave (B1 static waves)."""
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
for label, folder in (("B3 greedy", HERE), ("B1 wave", HERE.parent / "2026-10-06-g3-two-machines-cable-wave")):
    summary = json.loads((folder / "coordinator" / "summary.json").read_text())
    print(f"== {label}: outcome {summary['outcome']}, total {summary['total_seconds']:.1f} s, policy {summary['args']['policy']}, "
          f"code {summary['code']}")
    for g in summary["generations"]:
        print(f"  g{g['generation']}: wait {g['wait_seconds']:.1f} s, update {g['update_seconds']:.1f} s, publish {g['publish_seconds']:.2f} s, "
              f"total {g['total_seconds']:.1f} s, changed {g['changed']}, mean reward {g['mean_reward']:.4f}")
    for worker in ("5070ti", "1660s"):
        events = [json.loads(line) for line in (folder / f"worker-{worker}.jsonl").read_text().splitlines()]
        steps = [e for e in events if e["event"] == "step" and e["kind"] == "COMMITTED"]
        parts = {k: median(e["timing"][k] for e in steps) for k in ("perturb", "rollout", "restore", "total")}
        print(f"  worker {worker}: {len(steps)} candidates {[e['candidate_id'].split('/', 1)[1] for e in steps]}; median seconds per candidate "
              + ", ".join(f"{k} {v:.2f}" for k, v in parts.items()) + f"; exit {events[-1]['reason']}")
        for s in (e for e in events if e["event"] == "sync"):
            print(f"    sync {s['bytes']} bytes: transfer {s['transfer_seconds']:.1f} s, load {s['load_seconds']:.1f} s, rehash {s['rehash_seconds']:.1f} s")
    reference = json.loads((folder / "reference.json").read_text())
    print(f"  reference (one process, 5070 Ti): total {reference['total_seconds']:.1f} s")
