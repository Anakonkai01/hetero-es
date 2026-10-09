#!/usr/bin/env python3
"""Summarize run_probe.sh output: python summarize_probe.py <out dir>. Per K: seconds per condition (median over processes and conditions, parent excluded),
the throughput gain over K = 1 (K x t1 / tK, 1.0 = no gain, K = perfect), and whether every process gave the same texts as the K = 1 process."""
import json
import statistics
import sys
from pathlib import Path

out = Path(sys.argv[1])
runs = {}
for path in sorted(out.glob("k*-p*.json")):
    k = int(path.name.split("-")[0][1:])
    runs.setdefault(k, []).append(json.loads(path.read_text()))
base = None
reference_texts = [c["sha256"] for c in runs[1][0]["conditions"]] if 1 in runs else None
print(f"{'K':>2} {'procs':>5} {'s/condition':>12} {'gain':>6} {'same texts as K=1':>18} {'GPU':}")
for k in sorted(runs):
    times = [c["seconds"] for r in runs[k] for c in r["conditions"][1:]]
    t = statistics.median(times)
    base = base or t
    same = "n/a" if reference_texts is None else all([c["sha256"] for c in r["conditions"]] == reference_texts for r in runs[k])
    print(f"{k:>2} {len(runs[k]):>5} {t:>12.2f} {k * base / t:>6.2f} {str(same):>18} {runs[k][0]['environment'].get('gpu_name')}")
