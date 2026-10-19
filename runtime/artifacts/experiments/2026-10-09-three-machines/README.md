# Three machines: the 5070 Ti, the 1660S and the borrowed 3060 (08 to 09/10/2026)

Written by the AI, **not reviewed by the owner**. **INCOMPLETE: the three-machine condition (T3) did not run, because the 1660S went down three times (see "What went wrong").** What did run is reported as it is.

## Setup
The same experiment as `../2026-10-08-c1-v2/` (experiment id `c1v2`, N = 24 candidates, 3 generations, workload `cot_l1_q128`, CUDA noise engine, FP32 evaluation, chunk 64, greedy dispatch): only the set of machines changes. The coordinator and the 5070 Ti's worker are on the 5070 Ti; the 1660S is on the cable (10.10.10.x); the 3060 (Windows 11, WSL2 Ubuntu) is on the home wifi and reaches the coordinator through Tailscale (`http://100.110.165.40:8765`, the coordinator listens on 0.0.0.0, the firewall allows that port on the cable for the 1660S only and everything on `tailscale0`). The 3060 catches up with each new parent by the rule `auto` of its profile (`--third-replay auto`; the profile with the measured synchronization is `../2026-10-08-third-machine-3060/profile-3060-l1q128-cuda-with-sync.json`, a derived file), except in the last row, where it downloads (`never`). The predictions were written BEFORE the runs by `scripts/predict_cluster.py` (`prediction-3060-by-replay.json`, `prediction-3060-by-download.json`).

## Results (T = seconds per generation without generation 0; CB = T(B0) / T(condition))
| condition | runs | predicted T (s) | measured T (s) | predicted CB | measured CB | candidates done by the 1660S / the 3060 (of 72) | final weights |
|---|---|---|---|---|---|---|---|
| B0: 5070 Ti alone | 2 | 194.9 | 151.2 and 152.0 | 1.000 | 1.000 | - / - | reference |
| B3: + 1660S (forced) | 1 | 188.7 | 133.1 | 1.033 | 1.14 | 14 / - | equal to B0 |
| **T2: + 3060, the 3060 replays** | 2 | 152.3 | 117.0 and 117.6 | **1.28** | **1.29** | - / 19 | equal to B0 |
| T2 with the 3060 downloading (`never`) | 1 | 194.9 | 151.5 | 1.00 | 1.00 | - / 7 | equal to B0 |
| T3: all three | 0 | 131.6 | not run | 1.48 | not run | | |

* **The 3060 helps, and only because it replays.** With replay it catches up in 5.8 to 6.3 s per generation (estimated 5.3 s) and does 19 of 72 candidates; the cluster is 1.29 times faster than the 5070 Ti alone, and the prediction written before the runs said 1.28. With the full download over the wifi the first catch-up took 298 s (measured by `measure_sync.py`: 285 s), the 3060 did only 7 candidates and the time per generation is the 5070 Ti's own (CB 1.00), as predicted.
* **Same weights in all 6 valid runs**, hash of every generation equal to the single-machine reference of `c1-v2`, although the 3060 evaluated 19 of 72 candidates in each T2 run: on this workload (long, chunk 64, FP32, CUDA engine) the 5070 Ti and the 3060 give the same rewards.
* **Absolute times are over-predicted by about 30 percent** again (194.9 against 151.6 for B0; 152.3 against 117.3 for T2), the same bias as in `c1-v2` (profile candidate times higher than in the runs). The benefit, a ratio, is predicted much better than the time. The decision for the 1660S (B3) was wrong again (predicted +3.3 percent, measured +14 percent), consistently with `c1-v2`.
* B3 here is a single run, 133.1 s (CB 1.14); in `c1-v2` two runs gave 135.1 s (CB 1.12). The numbers agree.

## What went wrong
1. First attempt: the worker on the 3060 did not start in any run (a segmentation fault at the first CUDA kernel, after `apt install nvitop` had put the Ubuntu NVIDIA 580 libraries in the WSL; see `../2026-10-08-third-machine-3060/README.md`). The check added to `run_benchmark.py` that day reported "worker did not start" for those runs; they are kept as `invalid-3060-worker-segfaulted-*`. Fixed with `LD_LIBRARY_PATH` (`--third-env`).
2. The 1660S, in the night of 08/10, and again twice on the morning of 09/10 within minutes of being restarted (08:30 and 08:49), stopped answering under load (the owner's reading: a PCI/GPU contact fault; not verified in logs). Every run that had the 1660S after that point was reported as "worker did not start" and set aside as `*.failed-attempt*`; no run without its worker was counted. So B3 has one valid run (not two) and T3 none.

## What this does NOT show
The behaviour of all three machines together (T3 not run); more than one or two runs per condition; any link other than this wifi/Tailscale path (a second 3060 in another city is expected on 09/10); that the replay of the 3060 stays cheap over long chains (chains of 1 update here); a gain in a real learning run; the 3060 is a borrowed machine in WSL2 with software that is not byte-identical to the others (NumPy 2.5.3, Python 3.14.4).
