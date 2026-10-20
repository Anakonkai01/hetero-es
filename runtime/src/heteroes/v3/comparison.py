"""Paired checkpoint comparison: exact McNemar test and seeded paired percentile bootstrap.

McNemar uses the two-sided Binomial(n=fixed+broke, p=1/2) tail, as in statsmodels' exact implementation:
https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html
"""

import math


def _checkpoint(report, generation):
    checkpoints = report.get("checkpoints", [])
    selected = checkpoints[-1:] if generation is None else [c for c in checkpoints if c["generation"] == generation]
    if len(selected) != 1:
        raise ValueError("Select one recorded checkpoint")
    checkpoint = selected[0]
    scores = checkpoint.get("scores")
    if not isinstance(scores, list) or not scores or len(scores) != checkpoint.get("count"):
        raise ValueError("A paired comparison needs per-row scores and matching counts")
    if any(type(s) not in (int, float) or not math.isfinite(s) for s in scores):
        raise ValueError("Scores must be finite numbers")
    return checkpoint


def mcnemar_exact(fixed, broke):
    if any(type(n) is not int or n < 0 for n in (fixed, broke)):
        raise ValueError("Discordant counts must be nonnegative integers")
    n, k = fixed + broke, min(fixed, broke)
    if n == 0 or abs(fixed - broke) <= 1:
        return 1.0
    # Sum from the largest term downwards in log-scaled space; no factorial overflow for large datasets.
    term = total = 1.0
    for i in range(k, 0, -1):
        term *= i / (n - i + 1)
        total += term
        if term < total * 1e-16:
            break
    log_p = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) - n * math.log(2)
    return min(1.0, 2 * math.exp(log_p) * total)


def compare(a, b, generation_a=None, generation_b=None, *, resamples=10000, seed=11):
    import numpy as np

    if type(resamples) is not int or not 100 <= resamples <= 100000 or type(seed) is not int or seed < 0:
        raise ValueError("Use 100..100000 bootstrap resamples and a nonnegative integer seed")
    left, right = _checkpoint(a, generation_a), _checkpoint(b, generation_b)
    if (
        not a.get("rowsHash")
        or a["rowsHash"] != b.get("rowsHash")
        or not a.get("scorer")
        or a["scorer"] != b.get("scorer")
        or left["count"] != right["count"]
        or left["split"] != right["split"]
    ):
        raise ValueError("Paired reports require the same ordered rows, split and scorer")
    x, y = np.asarray(left["scores"], dtype=np.float64), np.asarray(right["scores"], dtype=np.float64)
    delta = y - x
    if not np.isfinite(delta).all():
        raise ValueError("Score differences must be finite")
    success_a, success_b = x == 1.0, y == 1.0
    fixed, broke = int(np.count_nonzero(~success_a & success_b)), int(np.count_nonzero(success_a & ~success_b))
    # A paired bootstrap draws the EMPIRICAL row deltas. Aggregating equal values into multinomial categories has
    # exactly that distribution while avoiding resamples x rows allocations for multi-million-row datasets.
    values, counts = np.unique(delta, return_counts=True)
    rng = np.random.default_rng(seed)
    sampled = []
    batch = max(1, min(128, 1_000_000 // len(values)))
    for offset in range(0, resamples, batch):
        draws = rng.multinomial(len(delta), counts / len(delta), size=min(batch, resamples - offset))
        sampled.extend((draws @ values / len(delta)).tolist())
    low, high = np.quantile(sampled, [0.025, 0.975], method="linear").tolist()
    return {
        "direction": "B minus A",
        "count": len(delta),
        "rowsHash": a["rowsHash"],
        "scorer": a["scorer"],
        "generationA": left["generation"],
        "generationB": right["generation"],
        "meanA": float(x.mean()),
        "meanB": float(y.mean()),
        "difference": float(delta.mean()),
        "successDefinition": "score == 1",
        "fixed": fixed,
        "broke": broke,
        "bothCorrect": int(np.count_nonzero(success_a & success_b)),
        "bothWrong": int(np.count_nonzero(~success_a & ~success_b)),
        "mcnemarExactP": mcnemar_exact(fixed, broke),
        "bootstrapCI": [low, high],
        "bootstrap": {"method": "paired-percentile", "confidence": 0.95, "resamples": resamples, "seed": seed},
    }
