# Replay as an option of the worker, on the two machines (08/10/2026)

Written by the AI, **not reviewed by the owner**. Code: `src/heteroes/replay.py`, `worker_runtime.py` (`bring_up_to_date`), `http_transport.py` (`GET /v1/updates/<parent sha256>`), `coordinator.py` (`_register_update`), `scripts/run_worker.py --replay`, `scripts/cluster_runner.py --replay`.

## What it does
When the job's parent weights are not the worker's, the worker either downloads them (1 GB) or fetches the coordinator's update records from the worker's weights to the job's (a few hundred bytes each), applies them with the engine of the recipe and compares the hash of its weights with the coordinator's child hash. Any problem (a missing or damaged record, a hash that differs, a network error) falls back to the full synchronization, which overwrites every weight. `--replay never` (default) downloads; `always` replays; `auto` replays only if the worker's own profile says that replaying is faster.

## Setup
The same experiment as B3 of `../2026-10-08-c1-v2/` (experiment id `c1v2`, N = 24, 3 generations, `cot_l1_q128`, CUDA engine, FP32, chunk 64, both workers, greedy dispatch): only the way the 1660S catches up with each new parent changes. `never` 2 runs, `always` 2 runs, `auto` 1 run (`run.sh`, `run2.sh`; the rule of `auto` read the 1660S profile `../2026-10-08-c1-v2/profile-1660s-l1q128-cuda.json`).

## Results
| mode | runs | final weights | candidates done by the 1660S (of 72) | catch-up of the 1660S, per generation | T per generation (steady, s) |
|---|---|---|---|---|---|
| never | 2 | **equal to the B0 run of c1-v2** in both | 14, 14 | sync 9.8 to 10.2 s (transfer 8.5, load 0.5, rehash 1.0) | 124.6 and 142.6; 124.1 and 146.0 |
| always | 2 | **equal to B0** in both | 13, 13 | replay 16.4 to 16.7 s = apply 12.56 s + check of the hash 3.8 to 4.2 s | 124.1 and 145.6; 126.5 and 145.6 |
| auto | 1 | **equal to B0** | 14 | declined replay every time ("estimated replay 16.8 s against synchronization 10.0 s"), then synchronized 9.8 to 10.2 s | 124.9 and 145.7 |

* **The weights are the same in all 5 runs and equal to the single-GPU run** (hash of each generation compared, not only the last). 10 replayed catch-ups on the 1660S (2 per `always` run) gave the coordinator's child hash every time.
* **On the direct gigabit cable replay is slower than the download** (16.5 s against 10 s), as the measurement of C4 said (12.3 s apply, plus the 3.8 s that the check costs); the rule of `auto` predicted 16.8 s and measured 16.5 s: the prediction from the profile was right to within 2 percent, and the decision (do not replay) was the faster one.
* The time per generation does not change with the mode: the catch-up of the 1660S is not on the critical path here, because the 5070 Ti does most of the candidates; this experiment does not show a speed gain of replay and was not meant to.
* The first attempt at `always` and `auto` is kept as `invalid-*` folders: the 1660S still ran the commit without `--replay`, its worker did not start (`unrecognized arguments`) and the run went on with the 5070 Ti alone while the harness said "ok". Not a result. (A weakness of `run_benchmark.py`: it does not fail when a remote worker does not start; every run here was checked by counting the candidates of the 1660S.)

## What this does NOT show
That replay is faster on any link (here it is not; the point of the option is a slower link or a faster GPU than the 1660S, not measured here: the wifi path to the 3060 is the intended test); a gain in the time of a generation; the optional early start when the record is written (not built); `--replay-verify-every` above 1 (tested with tiny models only: a trusted replay is not hashed until the next check, and a drift in between would not be seen); more than one lagging generation on real machines (the chain of two is tested on a tiny model only); one pair of GPUs, one workload, two or one repeats per mode.
