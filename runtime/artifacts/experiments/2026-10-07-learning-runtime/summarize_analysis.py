#!/usr/bin/env python3
"""Text summary of one or two `analyze_run.py` JSON files: checkpoints, the control (parent- and shuffled), the criteria. Usage: summarize_analysis.py analysis-runA.json [analysis-runB.json]"""
import json
import sys


def pct(x):
    return "  -  " if x is None else f"{100 * x:5.1f}"


def show(path: str) -> None:
    r = json.load(open(path))
    print(f"=== {r['experiment_id']}  (analysed {r['last_generation']} generations, checkpoints every {r['checkpoint_generations'][1] - r['checkpoint_generations'][0]})")
    print("\nCheckpoints: accuracy % (correct/n); `line` = share of replies with an Answer: line; `cond` = accuracy among them (H3); chars = mean reply length (H3)")
    print(f"{'gen':>4} {'train':>13} {'H3':>13} {'H1':>13} {'H2':>13} {'H3 line':>8} {'H3 cond':>8} {'H3 chars':>8}")
    for g, c in sorted(r["checkpoints"].items(), key=lambda kv: int(kv[0])):
        cells = " ".join(f"{pct(c[k]['accuracy'])} ({c[k]['correct']:>3}/{c[k]['n']:>3})" for k in ("train", "H3", "H1", "H2"))
        print(f"{g:>4} {cells} {pct(c['H3']['answer_line_rate']):>8} {pct(c['H3']['accuracy_with_line']):>8} {c['H3']['mean_chars']:8.0f}")
    print("\nControls every 10th generation (accuracy %, plus = the real step, minus = -alpha, shuf = coefficients shuffled), parent = before the step")
    print(f"{'gen':>4} | {'train +':>7} {'train -':>7} {'train s':>7} | {'H3 +':>6} {'H3 -':>6} {'H3 s':>6} | {'H3 line +':>9} {'line -':>7} {'line s':>7}")
    for g, c in sorted(r["controls"].items(), key=lambda kv: int(kv[0])):
        p, m, s = c["plus"], c["minus"], c["shuffled"]
        print(f"{g:>4} | {pct(p['train']['accuracy']):>7} {pct(m['train']['accuracy']):>7} {pct(s['train']['accuracy']):>7} | {pct(p['H3']['accuracy']):>6} {pct(m['H3']['accuracy']):>6} {pct(s['H3']['accuracy']):>6} | "
              f"{pct(p['H3']['answer_line_rate']):>9} {pct(m['H3']['answer_line_rate']):>7} {pct(s['H3']['answer_line_rate']):>7}")
    s2, h = r["s2"], r["s2_heldout_h3"]
    print(f"\nS2 on the training questions: parent+ better than parent- in {s2['positive']} of {s2['generations']} generations ({s2['negative']} worse, {s2['ties']} ties), "
          f"mean difference {s2['mean_diff']:+.4f}, one-sided sign test p = {s2['sign_test_p']:.2g}")
    print(f"S2 on H3 at the generations with held-out controls: + better in {h['positive']}, worse in {h['negative']} of {len(h['generations'])}")
    gens = r["generations"]
    cm = [(int(g), e["candidate_mean"]) for g, e in gens.items() if "candidate_mean" in e]
    cm.sort()
    print("Mean reward of the candidates (the population around the parent) every 10th generation: " + ", ".join(f"g{g}={v:.3f}" for g, v in cm if g % 10 == 0))
    print("Replay checks (rebuilt weights against the stored checkpoint hash): " + ("all MATCH" if all(v["match"] for v in r["replay"].values()) else "MISMATCH: " + str([g for g, v in r["replay"].items() if not v["match"]])) + f" ({len(r['replay'])} segments)")
    v = r["verdict"]
    print(f"\nVERDICT  S1={v['S1']} S2={v['S2']} S3={v['S3']} S4={v['S4']} S5={v['S5']}  ->  {v['label']}   [{v['note']}]\n")


for path in sys.argv[1:]:
    show(path)
