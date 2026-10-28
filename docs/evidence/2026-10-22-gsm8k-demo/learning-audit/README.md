# Why tier 3 did not learn: a read-only audit (2026-10-22)

Run `fa67c66c203a4afaaaad9f9215656e4d` (tier 3): full-parameter ES on Qwen2.5-0.5B-Instruct, GSM8K, N = 32 candidates
per generation, batch 32 questions, σ 1e-3 → 2.5e-4 (cosine over 300 generations), α = 5e-4 constant, `zscore@1`,
greedy decoding, 512 new tokens, no antithetic, no momentum. Validation (500 rows from the GSM8K train split):
base 0.608, generation 24 0.606, generation 49 0.572. The owner asked why the model does not get better, and whether
the system is right and the cause is the choice of hyperparameters. The run was stopped after this audit (owner's
decision; see `../RESULTS.md`, tier 3).

Everything here is measured on a copy of the ledger and on the run's weight files; nothing in the run was changed.
`learning_audit.py` reproduces every number; `audit.txt` is its output on the final ledger (71 applied updates,
2,304 results).

## What was measured

| Question | Measurement | Result |
| --- | --- | --- |
| Is the scorer wrong? | Score every stored completion again with `heteroes.study.evaluation.extract` | 0 of 2,304 rewards differ; validation `parseError` 0, truncated 9–14 of 500 at every checkpoint |
| Do devices disagree? | Cross-device audits in the ledger | 114 of 114 matched, no quarantine |
| Does float16 storage eat the update? | Two consecutive weight files (generations 69 → 70) | 95.5 % of parameters change; applied L2 1.966 vs requested α·√(Σz²)/N·√n = 1.965. Only parameters with abs(w) ≥ 0.25 (norm gains, ≈0.0 % of the parameters) mostly stay put |
| Is the update the documented one? | Same | yes: θ ← θ + α/N·Σ zᵢεᵢ, size as expected |
| Is there signal in a generation's rewards? | Var(candidate rewards) / the variance if each question were an independent coin per candidate | **1.01** (median 1.00): the spread is exactly what pure luck gives |
| Same, another way | Correlation of a candidate's score on one half of the batch with the other half | **0.001**: a candidate that does well on 16 questions does not do better on the other 16 |
| How much does σ change a candidate? | Answers per question across 32 candidates | 32 distinct answers on 99 % of questions; two candidates share a prefix of 42 characters (~10 tokens) |
| Are perturbed models worse? | Mean candidate reward over all generations | 0.497 vs ~0.61 for the unperturbed center (validation is drawn from the same train split) |
| Where does the center go? | L2 distance base → generation 70 | 16.57 against 16.55 for a random walk of 71 steps of 1.965 |
| Did validation really drop? | Paired comparison on the same 500 rows | base → 24: 57 right→wrong, 56 wrong→right (p = 1.0); base → 49: 66 vs 48 (McNemar p = 0.11, not significant) |

In words: at σ = 1e-3 a perturbed model's greedy answer is a fresh draw (it leaves the base text after ~10 tokens),
so which candidate scores best on 32 questions is luck. The z-score turns those rewards into a full-size step anyway
(z has unit spread whatever the rewards are), so the center walks randomly at ‖Δ‖ ≈ 1.97 per generation. Any real
gradient component is too small to detect in one generation (upper bound: true candidate differences are under ~6 % of
the noise variance).

## What the literature says (local copies in `.scratch/literature/papers/`)

- **Understanding ES for LLM Reasoning** (arXiv 2608.27351v2). Table 6: Qwen2.5-0.5B-Instruct on GSM8K, N = 32,
  batch 64: smoothed training reward (of the perturbed population) 0.510 → 0.518 → 0.525 at updates 100/200/300 — the
  same ~0.5 level we measure, and a gain of ~1.5 points over 200 updates. 0.5B is their hardest case (Appendix F: N = 8
  and 16 decline). Table 13: at σ = 1e-3, GSM8K rewards of +ε and −ε are almost uncorrelated (0.13 on 1.5B, common
  seed), so early divergence is normal for ES on reasoning, and antithetic (two-point) ES gives no advantage on GSM8K
  (§5.2). Their GSM8K recipe (Table 14): σ = 1.5e-3 constant, α = 2.5e-4, batch 64, 2 epochs, τ = 0.
- **Evolution Strategies at Scale** (arXiv 2509.24372v3). N = 30, σ = 1e-3, α = 5e-4, greedy, bfloat16 weights. The
  large 0.5B gain is on Countdown (Table 1: 0.1 % → 14.4 %). The GSM8K ablation (Tables 9–10) covers 1.5B/3B only and
  finds σ = 5e-4 worse than 1e-3 or 2e-3.
- **Agentic ESOpt** (arXiv 2608.17310v2). Tier 3's recipe (σ cosine 1e-3 → 2.5e-4, α = 5e-4, G = 32, 32 tasks per
  generation) is their Sudoku profile (Table 8): Qwen3.5-4B, 100 generations, sampling at τ = 0.7.

## Conclusion

1. **The system is right.** Distribution, audits, scoring, the update rule and float16 storage behave as specified;
   every check above is a measurement, not an assumption.
2. **The cause is not a single wrong hyperparameter.** For a 0.5B model on GSM8K the expected ES gain is ~1–3 points
   over hundreds of updates (Understanding ES, Table 6) — below what 500 validation rows resolve (SE ≈ 2.2 points). Not
   seeing a gain by generation 50 was the expected outcome.
3. **The recipe made it noisier than the GSM8K recipes in the literature.** It was taken from a 4B Sudoku setting:
   batch 32 instead of 64, α/σ = 0.5 instead of 0.17, and σ decays while α stays fixed, so by the end each random step
   would be ~35 % of σ. Random drift then dominates a small signal; the generation-49 drop is consistent with that but
   not significant.
4. **Correction of a first reading.** "σ is too large" and "turn on antithetic" are not supported: ES at Scale found a
   smaller σ worse, and Understanding ES found antithetic no better on GSM8K.

The project's claim is the system, not that ES learns (owner decision 2026-10-20); learning runs stay parked.

## Reproduce

```
PYTHONPATH=runtime/src ~/miniforge3/envs/heteroes-match/bin/python \
  docs/evidence/2026-10-22-gsm8k-demo/learning-audit/learning_audit.py \
  <copy of ledger.sqlite> fa67c66c203a4afaaaad9f9215656e4d \
  ~/.local/share/heteroes-worker/artifacts/study/datasets/1caae74d81892fe2f6af8d0dafb1a710312acdcd64eb3e16c24c524bd1af11e4.jsonl \
  --validation <run directory> --weights <base .bin> <generation 69 .bin> <generation 70 .bin>
```

The run directory and the weight files of generations 69 and 70 are archived in
`/mnt/Archive-2tb/heteroes-local/tier3-fa67c66c-20261022/` (`run-pre-cancel/`, `run-final/`, `weights/`); the base
file is the coordinator's `selection/c9118c8a….bin`. Limits: the noise distribution and the perturbation used during
evaluation were not re-derived here; they rest on the parity receipts (`../tier3/parity.json` and earlier tiers).
