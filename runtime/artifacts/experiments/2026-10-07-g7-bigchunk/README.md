# G7: the cluster benchmark with a bigger chunk (prompts per generate() call) (07/10/2026)

The same two machines, runtime and settings as `../2026-10-07-g7-cluster-benchmark/` (commit `f7dffb7` on both; CUDA noise engine, FP32 forward pass, N = 24, 4 generations, 3 runs per cell,
`run_campaign.sh`, `scripts/summarize_benchmark.py`, `summarize_workers.py` -> `summary-*.txt`), but with a bigger `--chunk`, after the exactness probe of `../2026-10-07-g7-restore-tradeoff/`
(`chunkprobe-*.json`: chunks 32 and 64 gave the same answers as chunk 16 for the parent and 24 perturbed candidates, 0 of 1,600 answers differ, on both GPUs and between them).
Two configurations (21 runs): **`cot_l3_q32` at chunk 32** (the workload of the previous benchmark: a pure speed comparison) and **`cot_l3_q64` at chunk 64** (twice the questions per candidate, the first 32 are the same).
The AI wrote and ran all of it; the owner has not reviewed it.

## Result

T of a generation (s), steady state (generations 1 to 3), 95 percent Student-t intervals over the runs:

| workload, chunk | condition | T (s) | 95 % | speed-up over the baseline | 95 % |
|---|---|---|---|---|---|
| 32 questions, chunk 32 | B0x2 (baseline) | 69.0 | 0.9 | 1.000 | 0.018 |
| | B3x2 (+ 1660S, greedy) | 65.7 | 0.4 | 1.051 | 0.015 |
| | **B4x2 (+ 1660S, tail-aware)** | **61.9** | 0.6 | **1.116** | 0.018 |
| 64 questions, chunk 64 | B0 (5070 Ti, one process, baseline) | 107.6 | 0.6 | 1.000 | 0.008 |
| | B0x2 (two processes) | 108.5 | 0.8 | 0.992 | 0.009 |
| | B3x2 (+ 1660S, greedy) | 90.6 | 1.0 | 1.188 | 0.015 |
| | **B4x2 (+ 1660S, tail-aware)** | **90.2** | 0.8 | **1.194** | 0.012 |

All 9 runs of the first configuration ended with the same rewards and weights hash (`6c5e4d82...`), and all 12 of the second (`eb8e5626...`), although the 1660S evaluated 11 to 16 of the 96 candidates of a run.

Against the first G7 benchmark (the same 32 questions, chunk 16): B0x2 99.5 s to 69.0 s (31 percent shorter), B3x2 104.3 s to 65.7 s (37 percent), B4x2 90.9 s to 61.9 s (32 percent). The best configuration against
the best one before G7 (CPU noise engine, B0x2, chunk 16: 107.5 s): **61.9 s, 42 percent shorter**. With 64 questions the generation takes 90.2 s, as long as the old B4x2 with 32 questions (90.9 s):
**twice the questions per candidate at the same time per generation** (17.0 questions evaluated per second against 8.4), which halves the variance of the reward of a candidate (not measured here).

Who did what (`summary-workers.txt`, mean per run of 96 candidates):

| workload, chunk | condition | candidates of the 1660S | of the two 5070 Ti processes | idle s of the 1660S / of a 5070 Ti process |
|---|---|---|---|---|
| q32, chunk 32 | B3x2 | 13.0 | 42.0 + 41.0 | 14 / 34 |
| q32, chunk 32 | B4x2 | 11.0 | 42.3 + 42.7 | 31 / 20 |
| q64, chunk 64 | B3x2 | 16.0 | 40.0 + 40.0 | 28 / 10 |
| q64, chunk 64 | B4x2 | 16.0 | 40.0 + 40.0 | 27 / 10 |

## What it says

- **The chunk was the lever.** The rollout is 92 to 96 percent of a candidate and its cost per step does not depend on the batch, so more prompts per call is almost free: 31 to 37 percent shorter generations from a change of one argument, with the same
  workload, the same noise and the same weights evolution rules; the answers were checked equal to those of chunk 16 first.
- **The second process on the 5070 Ti is useless for this workload**, as the earlier numbers suggested: one process (107.6 s) is as fast as two (108.5 s; 0.992 +- 0.009 against it). The baseline of the second configuration is therefore B0, not B0x2.
- **The 1660S is worth more with a big chunk:** 1.188 and 1.194 over the best single-machine configuration (1.094 at chunk 16). Its candidate takes 18.7 s against 4.4 s on the 5070 Ti (4.3 times, it was 7.5 times at chunk 16), so it does 16 of 96 candidates (17 percent).
  The ceiling of any scheduling for these two speeds is 1 + 4.4 / 18.7 = 1.23; the tail-aware run reaches 1.194 (about 80 percent of the possible gain; what is left is its 10 s of synchronization per generation, the 2.4 s update and the start of the 1660S after its first synchronization).
- **Greedy dispatch (B3) is no longer worse than tail-aware (B4) with 64 questions** (1.188 against 1.194, intervals overlap): with candidates of 4 s and 19 s the end of a generation has no long tail. With 32 questions at chunk 32 the tail-aware policy is still better (1.116 against 1.051).

## What it does NOT show

- N = 24 only; 3 runs per cell; one workload family (arithmetic with reasoning, 0.5B model); one pair of GPUs. Chunks above 64 were not tried (the 64-question workload cannot use them).
- The exactness of chunks 32 and 64 is a checked level (0 of 1,600 answers differ, on the parent and 24 perturbed candidates, both GPUs, FP32): an upper bound of about 0.2 percent per answer at 95 percent confidence, not a guarantee. The chunk is an execution choice of a worker, not part of the recipe: a worker with another chunk
  would silently give other answers if that level were wrong, so the probe has to be repeated for another model, workload or software version (`chunk_probe_cot.py`, `compare_chunk_probe.py`).
- The same chunk for both machines; a bigger chunk for the 1660S alone (it gains more) was not tried. The starting speeds of the tail-aware policy are derived estimates (`profiles-derived/`).
- No learning: the rewards and weights are equal in all runs of a configuration, but whether the weights move usefully over many generations is not analysed.
