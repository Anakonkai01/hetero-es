#!/usr/bin/env python3
"""
Table of the README: measured against the predictions written BEFORE the runs (prediction-n*.json, made by scripts/predict_cluster.py).
    PYTHONPATH=src python compare_prediction.py            (run from the repository root; reads summary-n48.json, summary-n96.json)
Candidates per generation = jobs of the run / 3 generations. T = steady-state seconds per generation (summarize_benchmark.py).
"""
import json
from pathlib import Path

D = Path(__file__).parent
GENERATIONS = 3
print("| N | condition | runs | predicted T (s) | measured T (s) | T error | predicted CB | measured CB | candidates per generation 5070 Ti / 3060, predicted | measured | same weights in every run |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for n in (48, 96):
    summary = json.loads((D / f"summary-n{n}.json").read_text())
    prediction = json.loads((D / f"prediction-n{n}.json").read_text())["predictions"]
    b0 = summary["conditions"][f"n{n}-B0"]
    t2 = summary["conditions"][f"n{n}-T2"]
    pred_b0 = prediction["worker-5070ti"]["B3_GREEDY_DYNAMIC"]
    pred_t2 = prediction["worker-5070ti+worker-3060"]["B3_GREEDY_DYNAMIC"]
    runs = {k: v for k, v in summary["runs"].items() if k.startswith(f"n{n}-T2")}
    jobs_5070 = sum(r["workers"]["5070ti"]["jobs"] for r in runs.values()) / len(runs) / GENERATIONS
    jobs_3060 = sum(r["workers"]["3060"]["jobs"] for r in runs.values()) / len(runs) / GENERATIONS
    T0 = b0["T_steady"]
    for label, cond, pred in (("B0", b0, pred_b0), ("T2 (+3060 by replay)", t2, pred_t2)):
        T = cond["T_steady"]
        cb_pred = pred["cluster_benefit_against_local_alone"]
        cb = T0 / T
        counts = f"{pred['jobs'].get('worker-5070ti', 0)} / {pred['jobs'].get('worker-3060', 0)}"
        measured = f"{jobs_5070:.1f} / {jobs_3060:.1f}" if label.startswith("T2") else f"{n} / 0"
        same = "yes" if summary["consistent"][f"n{n}"]["identical_rewards_and_hashes"] else "NO"
        print(f"| {n} | {label} | {cond['repeats']} | {pred['total_seconds']:.1f} | {T:.1f} | {100 * (pred['total_seconds'] - T) / T:+.0f}% | {cb_pred:.3f} | {cb:.3f} | {counts} | {measured} | {same} |")
