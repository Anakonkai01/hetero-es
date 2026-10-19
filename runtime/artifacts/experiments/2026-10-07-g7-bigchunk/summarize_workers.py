"""Who did what in the runs of the G7 bigger-chunk benchmark: candidates, busy, synchronization and idle seconds per run (mean over the runs), the time of each generation, and the
final weights hashes. Reads summary-cot_l3_q32-chunk32.json and summary-cot_l3_q64-chunk64.json (made by scripts/summarize_benchmark.py). Usage: python summarize_workers.py"""
import json, statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
for name in ("cot_l3_q32-chunk32", "cot_l3_q64-chunk64"):
    d = json.loads((HERE / f"summary-{name}.json").read_text())
    runs = list(d["runs"].values()) if isinstance(d["runs"], dict) else d["runs"]
    print(f"\n## {name}: {len(runs)} runs; distinct final weights hashes: {sorted({r['final_sha256'][:16] for r in runs})}\n")
    print("| condition | worker | candidates per run (of 96) | busy s | sync s | idle s |\n|---|---|---|---|---|---|")
    by = {}
    for r in runs:
        by.setdefault(r["run"].split("-")[1], []).append(r)
    for cond, rs in sorted(by.items()):
        for w in sorted({w for r in rs for w in r["workers"]}):
            ws = [r["workers"][w] for r in rs if w in r["workers"]]
            print(f"| {cond} | {w} | {st.mean(x['jobs'] for x in ws):.1f} | {st.mean(x['busy_seconds'] for x in ws):.0f} | {st.mean(x['sync_seconds'] for x in ws):.1f} | {st.mean(x['idle_seconds'] for x in ws):.0f} |")
