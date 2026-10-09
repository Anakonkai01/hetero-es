# N = 48 and N = 96 with the 5070 Ti and the borrowed 3060 (09/10/2026)

Written by the AI, **not reviewed by the owner**. Question: does the gain of a second, slower machine keep, or grow, when a generation has more candidates, and does the prediction written beforehand hold? The 1660S was down, so the pair is the 5070 Ti (coordinator and worker) and the 3060 (WSL2, home wifi through Tailscale, catching up by replay with the rule `auto`). Everything else as in `../2026-10-09-three-machines/`: `cot_l1_q128`, CUDA engine, FP32, chunk 64, greedy dispatch, 3 generations per run, experiment id `c1v2`. Predictions (`prediction-n48.json`, `prediction-n96.json`) were written by `scripts/predict_cluster.py` before the runs. `run.sh`, `run.out`.

## Results (T = seconds per generation without generation 0; CB = T(B0) / T(T2))
| N | runs per condition | B0: 5070 Ti alone, T | T2: + 3060, T | measured CB | predicted CB | candidates of the 3060 (of 3N) | replay of the 3060 per generation | predicted T (B0 / T2) |
|---|---|---|---|---|---|---|---|---|
| 24 (`../2026-10-09-three-machines`) | 2 | 151.6 | 117.3 | **1.29** | 1.28 | 19 of 72 | 5.8 to 6.3 s | 194.9 / 152.3 |
| 48 | 2 | 305.8 (306.1, 305.5) | 231.7 (230.9, 232.5) | **1.32** | 1.37 | 39 and 40 of 144 | 10.0 to 11.7 s | 389.1 / 284.9 |
| 96 | 1 | 623.2 | 468.7 | **1.33** | 1.37 | 76 of 288 | 19.1 and 19.3 s | 777.6 / 569.1 |

* **The gain grows a little with N and then stops: 1.29, 1.32, 1.33.** The ceiling of this pair is about 1.33 (a candidate takes about 6.9 s on the 5070 Ti and about 21 s on the 3060: 1 + 6.9/21), so at N = 96 the cluster is at the limit that the speeds allow: the fixed costs (update 4 s at N = 48, 7.5 s at N = 96, catch-up of the 3060, the tail) are small against the candidates.
* **The ratio is predicted to within 4 to 5 percent (1.37 against 1.32 and 1.33); the absolute times are over-predicted by 25 to 27 percent** (306 against 389, 623 against 778), the same bias as at N = 24 and in `../2026-10-08-c1-v2/` (the candidate times of the profiles are above those of the runs).
* **Same weights:** at each N all runs, B0 and T2, end with the same hash of every generation (4 runs at N = 48, 2 at N = 96): the 3060 evaluated 26 to 28 percent of the candidates and the result is that of the 5070 Ti alone.
* **Replay stays cheap:** it grows with N (0.19 s per candidate: 6 s, 11 s, 19 s) and remains far below the 285 s of the full download over this wifi.

## What this does NOT show
N = 96 is a single run per condition (no interval); one pair of machines, one workload, one link (home wifi through Tailscale); the 1660S and the three-machine condition are missing (the 1660S went down); N = 96 is still small against the hundreds of candidates and the many workers of the plan for later (that needs simulation and more machines); nothing about learning.
