# B0 and T2 with the default decode engine (the compacting decoder), 09/10/2026

Written by the AI, **not reviewed by the owner**. `run.sh`: `scripts/run_benchmark.py`, conditions B0 (the 5070 Ti alone) and T2 (the 5070 Ti + the first 3060, home wifi through Tailscale, replay always), 2 runs each in one session, N = 24, 3 generations,
workload `cot_l1_q128`, CUDA noise engine, FP32, chunk 64, experiment id `c1v2`. No `--decode-engine` option was given: the default of a long workload is now `hf_compact`. `summary.json` by `scripts/summarize_benchmark.py`.

## Results
| | T of a generation (steady state) | cluster benefit | candidates 5070 Ti / 3060 per run | idle 5070 Ti / 3060 per run |
|---|---|---|---|---|
| B0 | 93.7 +- 1.7 s | 1.00 | 72 / 0 | 6.5 and 7.5 s / - |
| T2 | 77.6 +- 21.1 s | 1.21 +- 0.33 | 55 / 17 and 54 / 18 | 12.8 and 24.5 s / 24.6 and 22.8 s |

* **All 4 runs ended with the same weights `a02a640b…`**, the hash of every earlier run of this experiment id with `generate()`; 0 failures. Rewards identical in the four runs (`identical_rewards_and_hashes: true`).
* For comparison with `generate()` the same day: B0 151.6 +- 5.0 s and T2 116.5 +- 1.9 s (cluster benefit 1.29 in `../2026-10-09-three-machines`); the compacting decoder made B0 1.6 times and T2 1.5 times faster. The two T2 runs here are 75.9 s and 79.2 s (generations 1 and 2); their interval is wide because two runs
  with a Student interval are wide, so 1.21 is NOT shown to be lower than 1.29.
* The 5070 Ti idled 13 to 25 s per run (about 4 to 8 s per generation), as with `generate()` (about 17 s): not enough for the tail-aware policy to matter (`../2026-10-09-dispatch-3060`, greedy kept).

## What this does NOT show
* Two runs per condition. The prediction columns are empty on purpose: the profiles passed were measured with `generate()` and do not describe the new engine (they need to be measured again).
* The first 3060 only, over the home wifi; not the 1660S (it went down four times that day, the last time minutes after it was started for a check of the compacting decoder on a Turing card: NOT done).
