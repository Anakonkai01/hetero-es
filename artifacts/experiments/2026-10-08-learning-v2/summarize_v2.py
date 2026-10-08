#!/usr/bin/env python3
"""Tables and the verdict (learnlib2.verdict, the criteria of PREREGISTRATION.md) of run D1, and the comparison of D2 with D1's generations 20-40.
Usage: summarize_v2.py analysis-runD1.json randomwalk-runD1-from20.json [analysis-runD2.json]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learnlib2 as l2  # noqa: E402

pct = lambda x: "  -  " if x is None else f"{100 * x:5.1f}"  # noqa: E731
r = json.loads(Path(sys.argv[1]).read_text())
walks = json.loads(Path(sys.argv[2]).read_text())
cps = {int(g): c for g, c in r["checkpoints"].items()}
last = max(cps)
print(f"=== {r['experiment_id']} (analysed {r['last_generation']} generations)\n")
print("Checkpoints, accuracy %  (H1 = test set of the training family, V1 = validation set of it, H2/H3 = other families)")
print(f"{'gen':>4} {'train':>6} {'H1':>6} {'V1':>6} {'H2':>6} {'H3':>6} | H1 line%  H1 acc|line  H1 chars")
for g in sorted(cps):
    c = cps[g]
    print(f"{g:>4} {pct(c['train']['accuracy']):>6} {pct(c['H1']['accuracy']):>6} {pct(c['V1']['accuracy']):>6} {pct(c['H2']['accuracy']):>6} {pct(c['H3']['accuracy']):>6} | {pct(c['H1']['answer_line_rate']):>8} {pct(c['H1']['accuracy_with_line']):>11} {c['H1']['mean_chars']:>9.0f}")
selected = l2.select_checkpoint({g: c["V1"]["accuracy"] for g, c in cps.items()})
last3 = sorted(cps)[-3:]
mean3 = {k: sum(cps[g][k]["accuracy"] for g in last3) / 3 for k in ("H2", "H3")}
s2 = r["s2"]
gens = [int(g) for g, e in r["generations"].items() if "diff" in e]
pos = sum(1 for g in gens if r["generations"][str(g)]["diff"] > 0)
neg = sum(1 for g in gens if r["generations"][str(g)]["diff"] < 0)
real_end = cps[last]["train"]["accuracy"]
walks_lower = [w[str(walks["steps"])]["train"]["accuracy"] < real_end for w in walks["walks"].values()]
v = l2.verdict(cps[0], cps[selected], pos, neg, mean3, walks_lower)
print(f"\nSelected checkpoint (best V1 after the base, earliest on a tie): generation {selected}")
print(f"P1 H1 {pct(cps[0]['H1']['accuracy'])} -> {pct(cps[selected]['H1']['accuracy'])}  ({100 * (cps[selected]['H1']['accuracy'] - cps[0]['H1']['accuracy']):+.1f} points, need +6.0): {v['P1']}")
print(f"P2 non-tie generations {pos + neg}: parent+ better in {pos}, worse in {neg} (ties {len(gens) - pos - neg}); sign test p = {l2.sign_test_p(pos, neg):.2g}; shuffled walks end at "
      + ", ".join(f"{100 * w[str(walks['steps'])]['train']['accuracy']:.1f}" for w in walks["walks"].values()) + f" against the real {100 * real_end:.1f} on train: {v['P2']}")
print(f"P3 train {pct(cps[0]['train']['accuracy'])} -> {pct(cps[selected]['train']['accuracy'])}  ({100 * (cps[selected]['train']['accuracy'] - cps[0]['train']['accuracy']):+.1f} points, need +8.0): {v['P3']}")
print(f"P4 mean of the last three checkpoints {last3}: H2 {100 * mean3['H2']:.1f} (base {pct(cps[0]['H2']['accuracy'])}), H3 {100 * mean3['H3']:.1f} (base {pct(cps[0]['H3']['accuracy'])}); each may be at most 6 points below the base: {v['P4']}")
print(f"\nVERDICT by the rule written in advance: {v['label']}")
if len(sys.argv) > 3:
    d2 = json.loads(Path(sys.argv[3]).read_text())
    c2 = {int(g): c for g, c in d2["checkpoints"].items()}
    print("\n=== D2 (exploratory, no verdict): from D1 generation 20, sigma 5e-4 alpha 7.5e-4, against D1 generations 20-40 (sigma 1e-3). accuracy %")
    print(f"{'step':>5} | {'D1 train':>8} {'D2 train':>8} | {'D1 H1':>6} {'D2 H1':>6} | {'D1 V1':>6} {'D2 V1':>6} | {'D1 H2':>6} {'D2 H2':>6} | {'D1 H3':>6} {'D2 H3':>6}")
    for step in sorted(c2):
        a, b = cps.get(20 + step), c2[step]
        if a is None:
            continue
        print(f"{step:>5} | {pct(a['train']['accuracy']):>8} {pct(b['train']['accuracy']):>8} | {pct(a['H1']['accuracy']):>6} {pct(b['H1']['accuracy']):>6} | {pct(a['V1']['accuracy']):>6} {pct(b['V1']['accuracy']):>6} | "
              f"{pct(a['H2']['accuracy']):>6} {pct(b['H2']['accuracy']):>6} | {pct(a['H3']['accuracy']):>6} {pct(b['H3']['accuracy']):>6}")
    g2 = d2["generations"]
    cm = [e["candidate_mean"] for e in g2.values() if "candidate_mean" in e]
    g1 = r["generations"]
    cm1 = [g1[str(k)]["candidate_mean"] for k in range(20, 40)]
    pa = [g1[str(k)]["train_parent"]["accuracy"] for k in range(20, 40)]
    pb = [e["train_parent"]["accuracy"] for e in g2.values() if "train_parent" in e and "candidate_mean" in e]
    print(f"mean reward of the 32 candidates in generations 20-39: D1 {100 * sum(cm1) / len(cm1):.1f} (parent {100 * sum(pa) / len(pa):.1f}); D2 {100 * sum(cm) / len(cm):.1f} (parent {100 * sum(pb) / len(pb):.1f})")
