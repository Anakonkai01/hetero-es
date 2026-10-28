# kill-worker and pause-worker on the long workload, three times each (08/10/2026)

Written by the AI, **not reviewed by the owner**. Why: in `../2026-10-08-failure-campaign-x3/` these two scenarios often did not happen (with the 16-prompt workload the 5070 Ti finished everything before the 1660S held a candidate). Here the workload is `cot_l1_q128` (CUDA noise engine, FP32, chunk 64, N = 8, 3 generations, lease 60 s): a candidate takes about 7 s on the 5070 Ti and 28 s on the 1660S, so the 1660S's worker holds a candidate for a long time and the scenario can always disturb it (`run.sh`, `rep1` to `rep3`).

## Result
Reference (the 5070 Ti alone) final weights: `a2123e795488fd6dd82465e83f5825b0c44c933b1760ad26711052f8a9c3a1c8`.

| scenario | what is done | rep 1 | rep 2 | rep 3 |
|---|---|---|---|---|
| kill-worker | SIGKILL of the 1660S's worker while it holds a candidate (found in the ledger), then a new process with the same worker id | pass | pass | pass |
| pause-worker | SIGSTOP of that worker for 75 s (lease 60 s), then SIGCONT: its late result must be refused | pass (1 late result refused, `stale_attempt`) | pass (1 refused) | pass (1 refused) |

All six scenarios happened (`exercised: true` in `verdicts.json`), ended normally and ended with the reference weights. With the three repeats of the short workload that did exercise `kill-worker` (2 of 3), `kill-worker` has 5 passes in 5 runs where it happened, `pause-worker` 3 in 3.

## What this does NOT show
The same limits as `../2026-10-08-failure-campaign-x3/README.md` (one disturbance at a time, two workers, a signal is not a failing machine, three repeats); the reference and the runs use the same workload, so "the same weights" is checked on a long evaluation here but only on N = 8; the refusal of the late result is visible in the log of the paused worker: in each of the 3 `pause-worker` runs exactly one step of kind `REFUSED` with code `stale_attempt` (and 3 committed candidates); no other log was analysed line by line.
