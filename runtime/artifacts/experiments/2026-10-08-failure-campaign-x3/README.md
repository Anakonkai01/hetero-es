# Failure campaign, five scenarios, three times each (08/10/2026)

Written by the AI, **not reviewed by the owner**. `scripts/failure_campaign.py`, the same as `../2026-10-07-g6-failure-campaign/` (coordinator and a worker on the 5070 Ti, a worker on the 1660S over the cable; N = 8, 3 generations, FP32, chunk 16, the 16-prompt workload, the CPU noise engine), plus one new scenario, run 3 times (`rep1`, `rep2`, `rep3`, `run.sh`). Every run is compared with the weights of the reference run (the 5070 Ti alone): `3577eadc3f22686a4a4f7fc1672fe9be255709676fdd701592b780616957e049`.

## Result
| scenario | what is done | rep 1 | rep 2 | rep 3 |
|---|---|---|---|---|
| cut-link | the packets from the 1660S are dropped for 8 s right after generation 0 is published | pass | pass | pass |
| kill-coordinator | SIGKILL in the middle of a generation (12 results committed), restart with `--resume` | pass | pass | pass |
| **kill-coordinator-mid-update (new)** | SIGKILL **between the write-ahead record of the update and the applied update** (found by polling the ledger every 20 ms; 8 results committed), restart with `--resume` | pass | pass | pass |
| kill-worker | SIGKILL of the 1660S's worker while it holds a candidate, then a new worker process with the same id | **not exercised** | pass | pass |
| pause-worker | SIGSTOP of the 1660S's worker for longer than the lease, then SIGCONT | **not exercised** | **not exercised** | **not exercised** |

"pass" = the run ended normally and its final weights hash is the reference. In 11 of the 15 runs the scenario happened and the system ended with the reference weights every time; **0 failures**.

**"Not exercised" is not a failure and not a pass.** The scenario waits for the 1660S's worker to hold a candidate before it disturbs it; with the 16-prompt workload a candidate takes a fraction of a second, so the 5070 Ti's worker often completes all 24 candidates before the worker on the other machine has started, and the wait times out after 600 s (`TimeoutError ... waiting for: the remote worker to hold a candidate`). Nothing was disturbed in those runs (the final weights were the reference's, as they should be). The verdict of the script (`verdicts.json`) says `passed: false` for them because it was written before `exercised` existed; the table above is the reading. The two scenarios that depend on the 1660S's worker were therefore repeated on a long workload where the 1660S always holds a candidate: `../2026-10-08-failure-campaign-long-workers/`.

## What this does NOT show
One disturbance at a time (no two failures together); two workers only; `kill -9` and a dropped link are not a machine that loses power or a GPU that falls off the bus (the 1660S does the latter by itself and was not part of this campaign); the first new scenario kills the process at one point of the window (the moment the polling sees the record), not at every possible instruction; 3 repeats per scenario are a small number; the workload is tiny (16 prompts), so the weights that are compared are those of a cheap evaluation.
