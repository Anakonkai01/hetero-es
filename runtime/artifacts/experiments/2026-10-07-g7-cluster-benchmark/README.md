# G7: the cluster benchmark with the long workload, CPU noise engine against CUDA noise engine (07/10/2026)

The two machines (RTX 5070 Ti + GTX 1660 SUPER, direct cable, torch 2.13.0+cu132 on both, both on commit `9548872`), the real runtime (coordinator, HTTP workers, ledger, full
synchronization), the long workload `cot_l3_q32` (word problems with reasoning, 32 questions, up to 256 tokens: `src/heteroes/eval/cot_workload.py`), FP32 forward pass, chunk 16,
N = 24 candidates, 4 generations per run, **3 runs of every condition and both noise engines (18 runs)**, by `run_campaign.sh`
(`scripts/run_benchmark.py`), summarized by `scripts/summarize_benchmark.py --baseline B0x2` (`summary-*-engine.txt`, `.json`) and `summarize_workers.py` (`summary-workers.txt`).
The headline is the steady state (generations 1 to 3; generation 0 is left out because the 1660S does not synchronize in it); the intervals are 95 percent Student-t intervals over the RUNS
(3 per cell, so they are wide on purpose). The AI wrote and ran all of it; the owner has not reviewed it.

Conditions: **B0x2** two worker processes on the 5070 Ti alone (the strongest single machine of G6, the baseline); **B3x2** the same + the 1660S, greedy dispatch; **B4x2** the same + the 1660S,
tail-aware dispatch (`GreedyTail`). The speeds that the tail-aware policy starts from are the medians of `../2026-10-07-g7-restore-tradeoff/` (`profiles-derived/`; it learns the real ones).

## Result

| noise engine | condition | T of a generation (s) | 95 % | speed-up over B0x2 of the same engine | 95 % |
|---|---|---|---|---|---|
| CPU (contract v1) | B0x2 | 107.5 | 1.3 | 1.000 | 0.017 |
| CPU | B3x2 | 107.4 | 13.3 | 1.001 | 0.125 |
| CPU | B4x2 | 101.2 | 5.8 | 1.061 | 0.062 |
| **CUDA** (contract section 16) | B0x2 | 99.5 | 0.2 | 1.000 | 0.003 |
| CUDA | B3x2 | 104.3 | 1.5 | 0.954 | 0.014 |
| CUDA | **B4x2** | **90.9** | 0.2 | **1.094** | 0.004 |

The CUDA engine against the CPU engine, same condition: B0x2 107.5 s to 99.5 s (7.4 percent shorter), B3x2 107.4 s to 104.3 s (2.9 percent, inside the interval of the CPU runs), B4x2 101.2 s to 90.9 s
(10.2 percent). The best configuration (CUDA engine, tail-aware, both machines) against the best one before G7 (CPU engine, the 5070 Ti alone, 107.5 s): **15.4 percent shorter**.

Who did what (`summary-workers.txt`, mean over the runs, 96 candidates per run):

| engine | condition | candidates of the 1660S | candidates of the two 5070 Ti processes | idle seconds of a 5070 Ti process (of about 400) | update s |
|---|---|---|---|---|---|
| CPU | B3x2 | 11.3 | 41.7 + 43.0 | 60 to 63 | 7.6 |
| CPU | B4x2 | 8.7 | 43.7 + 43.7 | 24 to 25 | 7.5 |
| CUDA | B3x2 | 12.7 | 41.7 + 41.7 | 80 to 81 | 2.4 |
| CUDA | B4x2 | 9.0 | 43.0 + 44.0 | 11 to 16 | 2.4 |

## What it says

- **The CUDA engine pays, but less than the single-process estimate suggested.** The estimate of `../2026-10-07-g7-restore-tradeoff/` (24 percent shorter) was for one worker process; with two processes on the
  GPU (B0x2) the second process already hides the CPU noise of the first, so what the CUDA engine removes here is mostly the update of the coordinator (7.5 s to 2.4 s per generation) and
  part of the noise: 7.4 percent. The gain grows when the CPU is the limit (the 1660S's candidates, B4x2: 10.2 percent).
- **With the long workload and the CUDA engine the 1660S is worth 9.4 percent of the speed of the best single machine, with tail-aware dispatch** (1.094 +- 0.004; in G6, with the 16-prompt workload and the CPU
  engine: 1.024 +- 0.023). It still evaluated only 9 of 96 candidates: a candidate takes it about 30 s against 4 to 5 s on the 5070 Ti (7 times), and its 30 s of synchronization per run (3 times 10 s)
  is a fixed cost. Greedy dispatch (B3x2) makes the cluster SLOWER than the 5070 Ti alone with the CUDA engine (0.954 +- 0.014): the 5070 Ti processes wait 80 s per run for the last candidate of the 1660S.
  The tail-aware policy is the whole difference between a loss of 4.6 percent and a gain of 9.4 percent.
- **Reproducibility across the two GPUs in a real distributed run.** In each engine all 9 runs ended with the same rewards and the same weights hash (CPU engine `49facf9b...`, CUDA engine `11d81a08...`),
  although the 1660S evaluated 9 to 13 candidates of every run in an order that changes from run to run. For the CUDA engine this is the same evidence as the single-process check
  (`../2026-10-07-g7-restore-tradeoff/cudaengine-*.json`), now with the runtime, the network, the dispatch and four generations of updates in between.
- The CPU engine's intervals are wide (B3x2 +- 13 s): the end of a generation depends on which candidate the 1660S takes last; with the CUDA engine the runs are stable (+- 0.2 to 1.5 s).
- Estimate against measurement (`../2026-10-07-g7-restore-tradeoff/sim-*.txt`, N = 24, against ONE process of the 5070 Ti, so only B4 and B3 can be compared as ratios): B4 CUDA 1.087 estimated, 1.094 measured; B4 CPU 1.091
  and 1.061 +- 0.062; B3 CUDA 0.983 and 0.954; B3 CPU 1.056 and 1.001 +- 0.125. The estimate was right about the sign and size of the tail-aware gain and optimistic about greedy dispatch.

## What it does NOT show

- One workload, one model (0.5B), one pair of GPUs, N = 24 only, 4 generations, 3 runs per cell (the CPU engine's intervals are wide). The synchronization of the 1660S (10 s per generation, 8.5 s of the gigabit link) is the same as in G6; the idea of a compressed delta is not tried.
- No learning: the rewards and the weights are the same in all runs of an engine, but whether the weights move in a useful direction over many generations is not analysed here.
- The priors of the tail-aware policy come from the single-process medians of the previous experiment, not from a profile made with the new workload (`profile_worker.py` still profiles the 16-prompt workload with the CPU engine); the policy learns the real speeds after the first candidates.
- The CUDA engine rests on two GPUs and one software stack agreeing on the numbers of curand (contract section 16): the self-test at the start of every worker and of the coordinator checks it, and has to be re-checked when torch or CUDA changes.
- A second worker process on the 5070 Ti shares the GPU with the coordinator's update; the absolute times are for this machine and these settings (coordinator update on 28 noise threads for the CPU engine).
