# Countdown ES pilot 1 (one RTX 5070 Ti) — 2026-10-19/20

Owner-authorized GPU. `heteroes run spec.json --device cuda --workers 2` at `393f366`: Qwen2.5-0.5B-Instruct, full
weights, N=32, σ=1e-3 constant, α=5e-4, `zscore@1`, antithetic off, 32 training prompts per generation, 512 new
tokens, chunk 64, `countdown@1` scorer, 30 generations, data `../2026-10-19-countdown-scorer` (2500 rows, seeded
80/10/10). About 6 minutes per generation. `generations.json`: per-generation mean/max candidate reward and update size.

## Result

Mean candidate reward 0.017 (generation 0) → 0.097 (generation 23) and flat afterwards, at the 0.1 format credit.
Scores of all stored texts (32 candidates × 32 rows):

| generation | 0.0 (no answer) | 0.1 (answer, wrong) | 1.0 (correct) | mean characters |
| --- | --- | --- | --- | --- |
| 0 | 847 | 177 | 0 | 1039 |
| 10 | 385 | 639 | 0 | 682 |
| 20 | 62 | 961 | 1 | 299 |
| 29 | 76 | 948 | 0 | 233 |

ES learned the answer format and much shorter answers within ~20 generations; it did not learn to solve the task.
Typical late answer: `<answer>(58 - 55) * 26 = 87</answer>` (wrong value, and the `= 87` makes it unparseable as an
expression, as in TinyZero's rule). Once nearly every candidate earns 0.1 on every row, the reward differences that
drive the update come from rare correct answers only (sparse reward).

Updates changed ~95% of the FP16 weights every generation (`changed`), so FP16 rounding did not swallow them.

## What this does NOT show

- One run, one seed, 30 generations (the paper reports 500 iterations); no validation/test evaluation of a
  checkpoint (the train texts already show ~0 correct). No claim that ES cannot learn Countdown here.
- Single machine; no audits across GPUs (audit rate 5%, both workers on the same GPU).
