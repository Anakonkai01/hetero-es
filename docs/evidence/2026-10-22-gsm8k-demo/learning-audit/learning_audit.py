"""Why a managed ES run did not learn: read-only measurements on its ledger (and optionally its weight files).

    PYTHONPATH=runtime/src python learning_audit.py <ledger.sqlite> <experiment id> <train split .jsonl> [--validation DIR] [--weights BASE PREV LAST]

Measures, per complete generation (32 candidates scored on the same batch):
  - rescore: the stored completions scored again must give the stored rewards (the scorer is not the cause);
  - noise ratio: Var(candidate rewards) / the variance if every question were an independent coin per candidate
    (1.0 = the ranking of candidates is all luck, no detectable skill);
  - split-half: correlation of a candidate's score on one half of the batch with the other half (0 = luck);
  - divergence: distinct answers per question and the shared prefix of two candidates' answers (how much sigma
    changes the text);
  - validation (--validation, the run directory's validation-*.json): paired right->wrong / wrong->right and McNemar;
  - weights (--weights, raw float16 files): the share of parameters one update changes in float16, applied vs
    requested step, and the drift from the base against a random walk.
Only the ledger copy is opened; nothing is written.
"""

import argparse
import json
import math
import os
import sqlite3
import zlib
from pathlib import Path

import numpy as np

from heteroes.study.evaluation import extract


def generations(ledger, experiment, train):
    db = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    batches = {
        g: json.loads(b)["batchIndices"] for g, b in db.execute("SELECT generation, body FROM generation_context")
    }
    rows = db.execute(
        "SELECT c.generation, c.candidate_index, r.reward, o.body FROM candidate c JOIN result r USING (candidate_id)"
        " JOIN completion o USING (candidate_id) WHERE c.experiment_id=?",
        (experiment,),
    ).fetchall()
    by, mismatches = {}, 0
    for generation, index, reward, body in rows:
        texts = json.loads(zlib.decompress(body))
        scores = [1.0 if extract(t) == train[j]["answer"] else 0.0 for t, j in zip(texts, batches[generation])]
        mismatches += abs(np.mean(scores) - reward) > 1e-9
        by.setdefault(generation, {})[index] = (scores, texts)
    complete = {g: [c[i] for i in sorted(c)] for g, c in by.items() if len(c) == 32}
    applied = db.execute(
        "SELECT count(*) FROM generation_update WHERE experiment_id=? AND applied_at IS NOT NULL", (experiment,)
    ).fetchone()[0]
    return complete, len(rows), mismatches, applied


def signal(complete):
    ratios, halves, means, flips = [], [], [], []
    for generation, candidates in sorted(complete.items()):
        m = np.array([scores for scores, _ in candidates])  # candidates x questions
        r, p = m.mean(1), m.mean(0)
        ratios.append(r.var() / ((p * (1 - p)).sum() / m.shape[1] ** 2))
        rng, corr = np.random.default_rng(generation), []
        for _ in range(200):
            order = rng.permutation(m.shape[1])
            a, b = m[:, order[: m.shape[1] // 2]].mean(1), m[:, order[m.shape[1] // 2 :]].mean(1)
            if a.std() > 0 and b.std() > 0:
                corr.append(np.corrcoef(a, b)[0, 1])
        halves.append(np.mean(corr))
        means.append(r.mean())
        flips.append(int(((p > 0) & (p < 1)).sum()))
    return np.array(ratios), np.array(halves), np.array(means), np.array(flips)


def divergence(complete):
    distinct, shared = [], []
    for generation in sorted(complete)[::5]:
        texts = [t for _, t in complete[generation]]
        for q in range(len(texts[0])):
            answers = [t[q] for t in texts]
            distinct.append(len(set(answers)))
            for i in range(0, len(answers) - 1, 2):
                a, b = answers[i], answers[i + 1]
                shared.append(len(os.path.commonprefix([a, b])))
    return np.array(distinct), np.array(shared)


def mcnemar(a, b):
    lost, gained = int(((a == 1) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
    n = lost + gained
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(lost, gained) + 1)) / 2**n) if n else 1.0
    return lost, gained, p


def weights(base_path, prev_path, last_path, alpha, population, steps):
    base, prev, last = (np.fromfile(p, dtype=np.float16) for p in (base_path, prev_path, last_path))
    step = last.astype(np.float32) - prev.astype(np.float32)
    drift = last.astype(np.float32) - base.astype(np.float32)
    requested = alpha / math.sqrt(population)  # per-parameter std of alpha/N * sum(z_i eps_i) with unit-variance z
    size = base.size
    print(f"weights: {size:,} parameters, base L2 {np.sqrt((base.astype(np.float64) ** 2).sum()):.1f}")
    print(
        f"  last step: {np.mean(step != 0) * 100:.1f}% of parameters changed in float16, applied L2"
        f" {np.sqrt((step.astype(np.float64) ** 2).sum()):.3f} vs requested {requested * math.sqrt(size):.3f}"
    )
    magnitude = np.abs(base.astype(np.float32))
    for low, high in [(0, 0.01), (0.01, 0.0625), (0.0625, 0.25), (0.25, 1), (1, math.inf)]:
        mask = (magnitude >= low) & (magnitude < high)
        if mask.any():
            print(
                f"    |w| in [{low:g}, {high:g}): {mask.mean() * 100:5.1f}% of parameters, changed {np.mean(step[mask] != 0) * 100:5.1f}%"
            )
    print(
        f"  drift from base after {steps} updates: L2 {np.sqrt((drift.astype(np.float64) ** 2).sum()):.2f},"
        f" random walk {requested * math.sqrt(size * steps):.2f}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ledger")
    parser.add_argument("experiment")
    parser.add_argument("train")
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--weights", nargs=3, metavar=("BASE", "PREV", "LAST"))
    parser.add_argument("--alpha", type=float, default=5e-4)
    args = parser.parse_args()
    train = [json.loads(line) for line in open(args.train)]
    complete, results, mismatches, applied = generations(args.ledger, args.experiment, train)
    print(
        f"results {results}, complete generations {len(complete)}, applied updates {applied},"
        f" rescore mismatches {mismatches}"
    )
    ratios, halves, means, flips = signal(complete)
    print(f"noise ratio: mean {ratios.mean():.2f}, median {np.median(ratios):.2f} (1.00 = ranking is luck)")
    print(f"split-half correlation: mean {halves.mean():.3f} (0 = ranking is luck)")
    print(f"questions that flip between candidates: {flips.mean():.1f} of 32 per generation")
    print(
        f"mean candidate reward: {means.mean():.3f}; first 20 generations {means[:20].mean():.3f}, last 20 {means[-20:].mean():.3f}"
    )
    print(f"corr(generation, mean candidate reward): {np.corrcoef(np.arange(len(means)), means)[0, 1]:.3f}")
    distinct, shared = divergence(complete)
    print(
        f"divergence: distinct answers per question {distinct.mean():.1f} of 32 ({np.mean(distinct == 32) * 100:.0f}% all"
        f" distinct); two candidates share a prefix of {int(np.median(shared))} characters (median)"
    )
    if args.validation:
        files = sorted(args.validation.glob("validation-*.json"), key=lambda p: int(p.stem.split("validation-")[1]))
        runs = [json.loads(p.read_text()) for p in files]
        for v in runs:
            truncated = sum(str(r.get("truncated")) == "True" for r in v["rows"])
            print(
                f"validation generation {v['generation']}: {v['meanReward']:.3f} (truncated {truncated}/{v['count']})"
            )
        base = np.array(runs[0]["scores"])
        for v in runs[1:]:
            lost, gained, p = mcnemar(base, np.array(v["scores"]))
            print(f"  base -> {v['generation']}: right->wrong {lost}, wrong->right {gained}, McNemar p {p:.3f}")
    if args.weights:
        weights(*args.weights, args.alpha, 32, applied)


if __name__ == "__main__":
    main()
