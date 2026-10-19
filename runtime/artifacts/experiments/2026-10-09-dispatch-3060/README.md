# Greedy (T2) against tail-aware (U2) with the 5070 Ti and the first 3060 (09/10/2026)

Written by the AI, **not reviewed by the owner**. N = 24, 3 generations, workload `cot_l1_q128`, CUDA engine, FP32, chunk 64, experiment id `c1v2`, replay always, home wifi through Tailscale. `run.sh` is the command (first launched with 3 repeats beside another job, stopped by the owner's request to cut long tests, relaunched with 2 repeats; `run-first-attempt-stopped.out` is the first log; `n24-U2-r1.failed-attempt1` is the run that was killed; `n24-T2-r1` had finished before the stop and was kept). U2 is a condition added to `scripts/run_benchmark.py` today: T2 with the tail policy (priors from the two profiles).

## Results (2 runs each, steady state = generations 1 and 2; `summary.json` by `scripts/summarize_benchmark.py`)
| | greedy (T2) | tail (U2) |
|---|---|---|
| T of a generation | 116.5 +- 1.9 s | 116.3 +- 3.5 s |
| idle time of the 5070 Ti per run | 17.0 and 17.3 s | 6.9 and 13.4 s |
| idle time of the 3060 per run | 31.2 and 23.3 s | 46.1 and 30.4 s |
| candidates 5070 Ti / 3060 per run | 53/19 and 52/20 | 54/18 and 52/20 |

All four runs ended with the same weights (`a02a640b…`).

**No measurable difference:** 116.5 against 116.3 s, intervals overlap. Tail made the 5070 Ti wait a little less and the 3060 a little more, but a generation did not get shorter. The AI's prediction (written in `TODO.md` before the runs: the 5070 Ti idles about 23 s per generation under greedy, so tail could save up to about 10 percent) was WRONG: the 5070 Ti idles about 17 s per run, about 6 s per generation; the 69 s used in the prediction came from the run with the second 3060 over a relay.

## What this does NOT show
* Two runs per policy, one pair of machines, one N: not a general statement about tail. With a much slower worker (the 1660S: 4 times slower) tail was slightly better in earlier G7 runs (1.194 against 1.188, intervals overlapping; FP16 chunk 1: 1.06 against 0.94).
* Not tested: a worker that disconnects (tail's 30 s window), three machines, N other than 24.
