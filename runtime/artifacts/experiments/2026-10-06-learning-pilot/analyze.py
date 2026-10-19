import json, sys, numpy as np
m = lambda v: sum(v) / len(v)
def analyze(path):
    r = json.load(open(path)); G = r["generations"]; n = len(G)
    held0, train0 = m(r["start"]["held"]), m(r["start"]["train"])
    q = r["held_size"]
    print(f"=== {path}  (alpha {r['config']['alpha']}, N {r['config']['population']}, sigma {r['config']['sigma']}, {n} generations)")
    print(f"start: train {train0:.4f}  held {held0:.4f}")
    print("gen | cand mean (min..max) | train parent->+ / - | held parent->+ / - | D_held(+ - -) | dTrain(+ - parent)")
    D, dtrain = [], []
    for g in G:
        pt, ph = m(g["parent"]["train"]), m(g["parent"]["held"])
        ptt, phh = m(g["plus"]["train"]), m(g["plus"]["held"])
        mt, mh = m(g["minus"]["train"]), m(g["minus"]["held"])
        D.append(phh - mh); dtrain.append(ptt - pt)
        print(f" {g['generation']:2d} | {np.mean(g['candidate_rewards']):.3f} ({min(g['candidate_rewards']):.3f}..{max(g['candidate_rewards']):.3f}) | {pt:.3f}->{ptt:.3f} / {mt:.3f} | {ph:.3f}->{phh:.3f} / {mh:.3f} | {D[-1]:+.3f} | {dtrain[-1]:+.3f}")
    final_held = m(G[-1]["plus"]["held"]); final_train = m(G[-1]["plus"]["train"])
    s1 = (final_held - held0) * q
    best_held = max(m(g["plus"]["held"]) for g in G); best_g = int(np.argmax([m(g["plus"]["held"]) for g in G]))
    print(f"final: train {final_train:.4f} held {final_held:.4f}  | held change {final_held-held0:+.4f} = {s1:+.0f} questions of {q}")
    print(f"best held along the trajectory: {best_held:.4f} at generation {best_g}")
    print(f"S1 (held >= +6 questions after {n} gen): {'YES' if s1 >= 6 else 'NO'}   ({s1:+.0f})")
    pos = sum(d > 0 for d in D)
    print(f"S2 (D_g > 0 in >= 8/10 and mean > 0): {pos}/{n} positive, mean D = {np.mean(D):+.3f} -> {'YES' if pos >= 8 and np.mean(D) > 0 and n == 10 else 'NO'}")
    print(f"S3 (mean train gain of + step > 0): mean {np.mean(dtrain):+.4f} -> {'YES' if np.mean(dtrain) > 0 else 'NO'}")
    held_gain = [m(g["plus"]["held"]) - m(g["parent"]["held"]) for g in G]
    print(f"held change of the + step per generation: {[round(x,3) for x in held_gain]}; mean {np.mean(held_gain):+.4f}; positive in {sum(x>0 for x in held_gain)}/{n}")
    cr = [np.mean(g["candidate_rewards"]) - m(g["parent"]["train"]) for g in G]
    print(f"mean (candidate reward - parent train reward) per generation: {[round(x,3) for x in cr]}; overall {np.mean(cr):+.3f}")
    print(f"applied/requested L2 {np.mean([g['applied_l2']/g['requested_l2'] for g in G]):.3f}; changed fraction {np.mean([g['changed']/g['numel'] for g in G]):.4f}; seconds/generation {np.mean([g['seconds'] for g in G]):.0f}")
    # train vs held trajectory of the real run
    print("train trajectory:", [round(train0,3)] + [round(m(g['plus']['train']),3) for g in G])
    print("held  trajectory:", [round(held0,3)] + [round(m(g['plus']['held']),3) for g in G])
for p in sys.argv[1:]: analyze(p); print()
