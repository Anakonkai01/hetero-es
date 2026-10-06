"""Print the numbers of the README from the raw files of this folder (run: python summarize.py)."""
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
for name in ("greedy-b3", "wave-b1"):
    summary = json.loads((HERE / name / "summary.json").read_text())
    print(f"== {name}: outcome {summary['outcome']}, total {summary['total_seconds']:.1f} s, policy {summary['args']['policy']}")
    for g in summary["generations"]:
        print(f"  g{g['generation']}: wait {g['wait_seconds']:.1f} s, record {g['record_seconds']:.3f} s, update {g['update_seconds']:.1f} s, "
              f"publish {g['publish_seconds']:.2f} s, mean reward {g['mean_reward']:.4f}, rewards {g['rewards']}")
    for worker in ("a", "b"):
        events = [json.loads(line) for line in (HERE / name / f"worker-{worker}.jsonl").read_text().splitlines()]
        steps = [e for e in events if e["event"] == "step" and e["kind"] == "COMMITTED"]
        syncs = [e for e in events if e["event"] == "sync"]
        parts = {k: median(e["timing"][k] for e in steps) for k in ("perturb", "rollout", "restore", "total")}
        coordination = median(e["coordination_seconds"] for e in steps)
        print(f"  worker {worker}: candidates {[e['candidate_id'].split('/', 1)[1] for e in steps]}; median seconds per candidate "
              + ", ".join(f"{k} {v:.2f}" for k, v in parts.items()) + f"; coordination {coordination:.3f}; exit {events[-1]['reason']}")
        for s in syncs:
            print(f"    sync {s['bytes']} bytes: transfer {s['transfer_seconds']:.2f} s, load {s['load_seconds']:.2f} s, rehash+snapshot {s['rehash_seconds']:.2f} s")
reference = json.loads((HERE / "reference.json").read_text())
print(f"== reference (one process): total {reference['total_seconds']:.1f} s; per candidate median "
      f"{median(t for g in reference['generations'] for t in g['candidate_seconds']):.2f} s; update median {median(g['update_seconds'] for g in reference['generations']):.1f} s")
