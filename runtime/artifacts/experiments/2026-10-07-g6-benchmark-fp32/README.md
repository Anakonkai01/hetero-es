# G6: the benchmark of the cluster with the FP32 forward pass, N = 24 (07/10/2026)

Both machines, the direct cable, torch 2.13.0+cu132 and transformers 5.17.0 on both (the 5070 Ti in `heteroes-match`), `--eval-dtype float32 --chunk 16` (numerical contract section 15),
N = 24 candidates, 4 generations per run, experiment id `g6bench`, lease 60 s with heartbeat, the coordinator's update on 28 noise threads and the workers' on 16.
**Five repeats of every condition** (20 runs), run in rounds (B0x2, B3x2, B4x2, B0, then again) by `scripts/run_benchmark.py`, summarized by `scripts/summarize_benchmark.py`
(`summary-n24-baseline-B0x2.json`, `summary-n24-baseline-B0.json`: raw per-generation times, per-worker jobs, busy, synchronization and idle time of every run). The unit of the 95 percent
Student-t intervals is the RUN (the mean of its generations 1 to 3: generation 0 is left out because the 1660S does not synchronize in it).

| condition | what runs | T of a generation (s) | 95 % | speed-up over B0x2 | 95 % |
|---|---|---|---|---|---|
| B0 | one worker process on the 5070 Ti | 35.9 | 0.2 | 0.82 | 0.01 |
| **B0x2** | two worker processes on the 5070 Ti (the strongest single machine) | **29.5** | 0.2 | 1.000 | |
| B3x2 | the same + the 1660S, greedy dispatch | 29.6 | 0.4 | 0.995 | 0.016 |
| B4x2 | the same + the 1660S, tail-aware dispatch (GreedyTail) | **28.8** | 0.6 | **1.024** | 0.023 |

A generation of B0x2 is about 21 s of candidates and 7.9 s of update (24 x 0.33 s, the CPU noise of the coordinator).

**What it says.**

- **All 20 runs ended with the same rewards and the same weights hashes** (`consistent`: 1 distinct value over 20 runs), although the 1660S evaluated 8 of the 96 candidates of a run (greedy) or 5.6 (tail-aware) and the 5070 Ti the rest, in an order
  that changes from run to run. With the FP32 forward pass the two GPUs agree on every answer (`../2026-10-07-g6-cross-gpu/`), so the final weights do not depend on who evaluated what. In G5 (FP16) this could not be promised.
- **The 1660S adds almost nothing at this scale.** With greedy dispatch the cluster is as fast as two processes on the 5070 Ti (0.995 +- 0.016: the difference is not measurable); with the tail-aware policy it is
  2.4 percent faster (1.024 +- 0.023, an interval that just excludes 1.0). Why: per generation the 1660S spends 10 s synchronizing (transfer 8.5 s over the gigabit cable, `sync` in the per-worker table of the summary: 29.9 s per run of 3 synchronizations),
  and a candidate costs it 4.9 s (3.3 s of CPU noise on a 2012 Xeon, 1.6 s of GPU) against 1.0 s on the 5070 Ti: in a generation of 29 s it works about 14 s, which is 2 to 3 candidates of 24. Plain greedy gives it those
  candidates and then waits for it at the end of the generation (the tail); `GreedyTail` keeps it away from the last candidates, which is the 0.8 s.
- A second worker process on the 5070 Ti is worth 1.22 times (35.9 s to 29.5 s): the GPU is idle during the CPU noise of a candidate (0.72 s of the 1.02 s).
- Against G5 (N = 24, B0, FP16, one prompt per call): 221 s per generation; **now 28.8 s to 29.5 s, about 7.5 times faster** for the same N, with the two GPUs or without the 1660S.

**What it does NOT show.** Only N = 24 and 4 generations here (`../2026-10-07-g6-benchmark-fp32-n96/` has N = 96); one pair of GPUs; a workload whose rollout takes 0.16 s on the fast GPU (so the CPU noise and the update, not the GPU, set the
speed); no learning (the weights move, but whether they move in a useful direction is the business of the learning experiments). The bound for this pair: a GPU that needs 4.9 s where the other needs 1.0 s is 20 percent of its
capacity at best, and its fixed 10 s synchronization per generation eats most of that at N = 24; the measured gain (0 to 2.4 percent) is consistent with it.
