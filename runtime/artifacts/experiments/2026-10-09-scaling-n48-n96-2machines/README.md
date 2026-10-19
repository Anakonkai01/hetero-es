# N = 48 and N = 96 with the 5070 Ti and the borrowed 3060 (09/10/2026)

Written by the AI, **not reviewed by the owner**. Every number below is in `comparison-table.md`, made by `compare_prediction.py` from `summary-n48.json` and `summary-n96.json` (made by `scripts/summarize_benchmark.py`) and the predictions written BEFORE the runs (`prediction-n48.json`, `prediction-n96.json`, `scripts/predict_cluster.py`). The runs are the ones of `run.sh`; `run.out` is its log.

## Setup
As `../2026-10-09-three-machines/`: workload `cot_l1_q128`, CUDA noise engine, FP32 evaluation, chunk 64 on both workers, greedy dispatch, 3 generations, experiment id `c1v2`. Conditions: **B0** = the 5070 Ti alone; **T2** = the 5070 Ti + the borrowed 3060 (home wifi, through Tailscale), the 3060 catching up with each new parent by replay (`--third-replay auto`, which chose replay). N = 48: 2 runs per condition. N = 96: 1 run per condition. The 1660S was down and is not part of it.

## Results (steady state: generation 0 left out, as in `summarize_benchmark.py`)
See `comparison-table.md` (copied here when the run finished):

| N | condition | runs | predicted T (s) | measured T (s) | T error | predicted CB | measured CB | candidates per generation 5070 Ti / 3060, predicted | measured |
|---|---|---|---|---|---|---|---|---|---|
| 48 | B0 | 2 | 389.1 | 305.8 | +27% | 1.000 | 1.000 | 48 / 0 | 48 / 0 |
| 48 | T2 | 2 | 284.9 | 231.7 | +23% | 1.366 | 1.320 | 35 / 13 | 34.8 / 13.2 |
| 96 | B0 | 1 | 777.6 | 623.2 | +25% | 1.000 | 1.000 | 96 / 0 | 96 / 0 |
| 96 | T2 | 1 | 569.1 | 468.7 | +21% | 1.366 | 1.330 | 70 / 26 | 70.7 / 25.3 |

* **The 3060 helps at both sizes, by about the predicted amount**: the cluster is 1.32 (N = 48) and 1.33 (N = 96) times faster than the 5070 Ti alone; predicted 1.366. The prediction is about 3 to 4 percent too high for the benefit.
* **The split of work is predicted well**: 13 of 48 and 26 of 96 candidates for the 3060 predicted, 13.2 and 25.3 measured.
* **Absolute times are over-predicted by 21 to 27 percent** again, the same bias as in `c1-v2` and `three-machines` (the profile's candidate times are above the real ones; cause not isolated). A ratio is predicted better than a time.
* **Same weights**: at each N, the final weights hash and all rewards are identical in every run, B0 and T2 together (4 runs at N = 48, 2 at N = 96; `summary-n*.json`, field `consistent`). The 3060 evaluated about a quarter of the candidates, so the 5070 Ti and the 3060 gave the same rewards on this workload. (Hashes of different N are different experiments and are not compared.)
* The benefit did not grow from N = 48 to N = 96 (1.32 to 1.33): with a catch-up of a few seconds against several hundred seconds per generation, this is expected; the replay is not yet a limit at two workers.

## What this does NOT show
* Anything about more than two workers (no three-machine run: the 1660S was down; the scaling with many workers is a simulation question, see `docs/planning/`). Two machines at two sizes are two points, not a curve.
* N = 96 has ONE run per condition (no interval); N = 48 has two (the interval in `summary-n48.json` is a Student interval over 2 runs, wide on purpose).
* A chunk per worker (both used 64) and a gain in a real learning run.
* A link other than the home wifi through Tailscale; chains of replay longer than 1 update.
* Only small network commands (a traceroute and a few curls, about 09:30) ran on the 5070 Ti beside the runs; no test suite and no GPU job.
