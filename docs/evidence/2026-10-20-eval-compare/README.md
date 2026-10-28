# Checkpoint evaluation and paired comparison (2026-10-20)

`heteroes eval` promotes the checkpoint replay script into an installed runtime module. The script is a compatibility
wrapper. Reports bind ordered rows and scorer identity, retain per-row scores, and optionally collect seeded sampled
outputs with Pass@K and majority voting. `heteroes compare` computes paired reward differences, success transitions,
two-sided exact McNemar p-values and a seeded paired percentile bootstrap CI. Equal empirical deltas are grouped for
multinomial resampling to avoid allocating a resamples-by-rows matrix.

`before.log` records nine failures before implementation. `first.log` records 13 passing tests; `regressions.log` records
14 passing tests after adding exact small-integer binomial oracle comparisons, large-count checks and non-default ledger
experiment identity. The tiny offline causal model runs a real ES generation, replays its checkpoint, samples twice with
the same seeds, compares the reports and refuses an existing output path. Negative cases cover malformed scores, row/scorer
mismatch and replay corruption. `mutation.log` records deliberate faults and their controls.

Statistical definitions follow the [Pass@K paper](https://arxiv.org/abs/2107.03374) and
[statsmodels' exact McNemar test](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html).
No SciPy or statsmodels dependency is added.

## What this does NOT show

- No GPU/model compatibility, Windows or real multi-machine acceptance is established by these offline CPU tests.
- No learning benefit is claimed. A paired test-set interval is not uncertainty over independent training runs.
- Sampling uses HF generation only. Arbitrary Python/expression rewards vote on complete texts; no generic semantic answer
  extractor is inferred for them. Success for sampled metrics and McNemar is the documented score-equals-one rule.
- The checkpoint evaluator consumes local JSON dataset documents; file-backed managed datasets need their local split
  objects. Native CUDA-noise replay selects the CUDA update implementation and needs a suitable GPU; the new tests use
  the canonical CPU noise engine.
