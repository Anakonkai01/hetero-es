# G6: the same benchmark with the FP16 reference evaluation (one prompt per call), N = 24 (07/10/2026)

The evaluation of G3 to G5 (FP16 forward pass, `--eval-dtype float16 --chunk 1`) on the code of G6, both machines on torch 2.13.0+cu132 and transformers 5.17.0, N = 24, 4 generations, experiment id `g6bench`, lease 60 s
with heartbeat. **Three repeats** of B0 (the 5070 Ti alone, one process), B3 (greedy, both) and B4 (tail-aware, both), in rounds; `summary-n24-baseline-B0.json` has the raw numbers. Steady state
(generations 1 to 3), 95 percent Student-t intervals over runs.

| condition | T of a generation (s) | 95 % | speed-up over B0 | 95 % | 1660S: candidates per run (of 96) | 1660S: synchronization per run |
|---|---|---|---|---|---|---|
| B0 | 48.3 | 0.7 | 1.000 | | | |
| B3 greedy | 51.3 | 1.4 | **0.941** | 0.030 | 12 | 30 s |
| B4 tail-aware | 45.5 | 1.8 | **1.060** | 0.046 | 8 | 30 s |

**Readings.**

- With plain greedy dispatch the cluster is 6 percent SLOWER than the 5070 Ti alone (an interval that excludes 1): the 1660S needs 11.4 s per candidate, takes a few, and the generation waits for it at the end (the tail), on top of 10 s of
  synchronization per generation. G5 had measured B3 as 3.5 percent faster than B0 at N = 24; that came from generation 0 (see STATUS 0.000) and does not hold.
- The tail-aware policy (B4, `GreedyTail`: a slow worker does not take a candidate when the faster ones would finish it sooner) turns it into a 6 percent GAIN (1.060 +- 0.046). The same policy is 2.4 percent better than two processes on the 5070 Ti with the FP32 evaluation
  (`../2026-10-07-g6-benchmark-fp32/`). With a slow GPU in the pool, WHO gets the last candidates matters more than anything else the cluster does.
- **The runs did not all end with the same weights.** Of the 9 runs, 7 ended with the final weights `c4cd67ea...` (the three B0 runs, four of the six runs that used the 1660S) and 2 (B3 repeat 1, B4 repeat 2) with `12d24fe8...`. In those two a candidate evaluated by the
  1660S gave another reward than it would have given on the 5070 Ti (one question of 16 differs; generation 0 was the same in all runs, the divergence came later), the update differed, and every following generation with it. This is the FP16 finding of
  `../2026-10-07-g6-cross-gpu/` seen at run level: the result of an FP16 run that uses both GPUs depends on which GPU evaluated which candidate. With the FP32 evaluation all 20 runs of the larger benchmark ended with identical weights.
- A generation is 48 s here (FP16, one prompt per call) against 36 s with the FP32 evaluation and chunk 16 on the same single process (`../2026-10-07-g6-benchmark-fp32/`), and 221 s in G5.

**Not shown:** three repeats only (the intervals are wide); N = 24 only; the divergence rate (2 of 6 mixed runs) is a rough number (about 60 evaluations on the 1660S in all).
