# A run cancelled before its coordinator accepted it is released (2026-10-20, session 5)

Found during the first managed `serve --lab` run on candidate3 (see `2026-10-20-managed-python-coordinator`): the
coordinator agent refused COORDINATE, the researcher cancelled, the agent acknowledged CANCEL_ASSIGNMENT and then
acknowledged COORDINATE as cancelled. Both devices reported their processes stopped, yet the experiment stayed STARTING
and both devices stayed allocated: `_release_confirmed` only releases an assignment whose runner snapshot is quiescent, and
an assignment that was never accepted has no runner to report one.

Now, only when the run has `cancelRequested`, the snapshot is still the lab-created STARTING one, and every selected device
has recently confirmed its coordinator/worker process stopped, the lab marks the snapshot CANCELLED and releases it. Without
a cancel request the lab keeps waiting (the second test case), so no outcome is invented for a slow coordinator.
`before.log` (red), `after.log` (58 pause/device/admission/policy/protocol tests), mutation 3/3.

## What this does NOT show

A CPU route test. The real release of the stuck candidate3 experiment is checked after the lab upgrade (later evidence).
