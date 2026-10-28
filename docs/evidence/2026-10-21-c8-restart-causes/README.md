# Why candidate8 restarted nobody on the real machines, and the fix

2026-10-21, after the candidate8 final run `a78af4b3…8604` (`../2026-10-21-long-multimachine-run-candidate8/RESULTS.md`).
Both causes were found from that run's own records (the isolated lab's `product.sqlite`, read-only, and the coordinator's
`lifecycle.jsonl` on Thao WSL, read over SSH). Then a test reproduced each one and failed before the fix.

## 1. Thao Windows: the 409 hypothesis is confirmed

- Lab audit: `DEVICE_QUALIFICATION_UPDATED` for the Windows device at 14:20:59 and 14:21:28 (before the run), then **none**
  during the run although the app was started again at 14:45 and kept starting new agents. The next one is at
  15:03:54, right when the run ended and released the GPU.
- Code: `PATCH /api/v1/device/qualification` (`backend/devices.py`) answered 409 while the device was reserved. `startAgent`
  (`desktop/worker/electron/service.cjs`) retried 20 × 200 ms, then stopped the agent (it was drained). That path did not
  call `recordAgentFailure`, so nothing was logged and no retry delay was set. The next status poll (3 s) started a new
  agent with a new `bootId`, so contribution was OFF again. That is the ~10 s cycle seen on the machine.
- The PATCH was always a repeat. The new agent's first poll already sends the same `selfTest` and the lab stores it, which
  is allowed while reserved when the GPU is the same (`agent_polling._refresh_observation`).

Fix: the lab accepts a qualification that is identical to the stored one for the current boot as a no-op
(`{"updated": false}`), even while reserved. Changed evidence still needs OFF, drained and no reservation. The app now
records a refused startup like any other agent failure: it logs one line (`agent failed`, `code`) and waits 30 s before
the next try.

## 2. 1660S after rejoining: the lab released it a second time

- Lab: after the second JOIN (1792569369), `assignments.body.workerDevices` and `computeGrants` of the run **lack** the
  1660S (they are still in the DB). No `START_WORKER launch 1` was ever queued.
- Coordinator `lifecycle.jsonl`: `worker_left` (g42), then nothing for the 1660S, and no `worker_restarted`.
- Cause: until its next generation boundary, the coordinator's reports still list the worker in `membership.left`, and
  its worker state still says `left`. `release_left_members` read that old view right after the JOIN. It released the
  device again and removed it from `workerDevices`. Every probe from the supervisor then got 403 ("Device is not
  authorized for this assignment"), and `_restart_members` hid that error.

Fixes:
- `release_left_members` ignores a worker the lab currently counts as a member (`intended_members`: the submitted
  workers plus every JOIN and LEAVE, in order).
- `_restart_members` logs `worker_restart_deferred` with `error` and `httpStatus`, once for each different reason and
  again after a successful restart. 503 means away, 409 means OFF, 403 means not in the assignment.

## Receipts (CPU only)

- New tests, each failing before its fix: `test_an_app_started_again_during_a_run_may_send_the_same_qualification`
  (backend), the rejoin part of `test_a_left_worker_releases_its_gpu_once_the_coordinator_confirms_it_stopped` (backend; it
  reproduced the exact c8 state, `workerDevices` without the worker),
  `test_a_member_not_started_again_says_why_once_per_reason` (runtime), and
  `a refused startup qualification is logged once and the agent waits before it starts again` (desktop worker).
- Suites after the fix: backend 394 passed; runtime 2584 passed, 102 skipped; desktop worker 89 passed.
- `mutation.log`: 11/11 mutants killed (`mutate.py`, on a scratch copy of `runtime/`, `backend/` and `desktop/worker/`).
  The first run left one mutant alive (forgetting the logged reason after a successful restart); a test was added for it.

## What this does NOT show

No device and no live run yet. These fixes need candidate9 on every device, then a live receipt for each fault. The
Windows path after the agent stays up (old worker reported stopped by the new boot, then `START_WORKER launch 1`) has
only unit-test evidence. The Linux CLI `kill -9` restart is still untested on hardware. Nothing was published,
deployed or pushed.
