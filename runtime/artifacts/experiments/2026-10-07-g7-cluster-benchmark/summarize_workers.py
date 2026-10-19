"""Per-condition table of who did what in the runs of the G7 cluster benchmark (candidates, busy, synchronization and idle seconds per run, mean over the runs),
the time of each generation, and the final weights hashes. Reads summary-cpu-engine.json and summary-cuda-engine.json (made by scripts/summarize_benchmark.py).
Usage: python summarize_workers.py"""
import json, statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
for engine in ("cpu", "cuda"):
    d = json.loads((HERE / f"summary-{engine}-engine.json").read_text())
    runs = list(d["runs"].values()) if isinstance(d["runs"], dict) else d["runs"]
    print(f"\n## {engine} noise engine: {len(runs)} runs; distinct final weights hashes: {sorted({r['final_sha256'][:16] for r in runs})}\n")
    print("| condition | worker | candidates per run (of 96) | busy s | sync s | idle s |\n|---|---|---|---|---|---|")
    by = {}
    for r in runs:
        by.setdefault(r["run"].split("-")[1], []).append(r)
    for cond, rs in by.items():
        for w in sorted({w for r in rs for w in r["workers"]}):
            ws = [r["workers"][w] for r in rs if w in r["workers"]]
            print(f"| {cond} | {w} | {st.mean(x['jobs'] for x in ws):.1f} | {st.mean(x['busy_seconds'] for x in ws):.0f} | {st.mean(x['sync_seconds'] for x in ws):.1f} | {st.mean(x['idle_seconds'] for x in ws):.0f} |")
    print("\n| condition | generation 0 | 1 | 2 | 3 (seconds, mean over the runs) |\n|---|---|---|---|---|")
    for cond, rs in by.items():
        print(f"| {cond} | " + " | ".join(f"{st.mean(r['generation_seconds'][i] for r in rs):.1f}" for i in range(4)) + " |")
