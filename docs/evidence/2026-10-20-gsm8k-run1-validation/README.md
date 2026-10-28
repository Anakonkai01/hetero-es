# GSM8K run 1 (stopped after 30 generations) — validation of checkpoints

Run: Qwen2.5-0.5B-Instruct, full weights, N=32, sigma 1e-3, alpha 5e-4, zscore@1, batch 32 of 2,000 train rows,
512 new tokens, greedy, scorer `answer-line-last-number@1`; `spec.json` is the planned 60-generation spec. The owner
stopped it by SIGTERM after generation 29 was published (30 generations; ledger replay hashes verified).
Validation = 500 rows of `dataset-meta.json`'s validation split, never used for updates.

| Checkpoint | correct / 500 | mean | truncated |
|---|---|---|---|
| -1 (base) | 281 | 0.562 | 20 |
| 9 | 272 | 0.544 | 19 |
| 19 | 278 | 0.556 | 17 |
| 29 | 278 | 0.556 | 24 |

Paired against the base: gen 9 fixed 45 / broke 54, gen 19 fixed 49 / broke 52, gen 29 fixed 60 / broke 63.
Full per-row outputs stay in `.scratch/gsm8k/eval/validation-g29.json` (not committed).

## What this does NOT show
- No improvement and no harm: the differences are inside the sampling noise of 500 rows (about 0.022).
- Nothing about the planned 60 generations, other seeds, other hyper-parameters or the GSM8K test split.
- Nothing about forgetting (CommonsenseQA not scored yet) or about sampled/Pass@K decoding.
- It does not show that ES cannot learn here: 30 steps of 32 rows is far smaller than the reference papers.
