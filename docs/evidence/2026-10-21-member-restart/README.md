# A member that comes back is started again (ADR-009 item 8)

2026-10-21. Owner request ("sửa luôn") after the candidate7 acceptance run: Thao's Windows 3060 was hard-stopped at g19,
relaunched and turned ON, but got no more work until the end of the run.

## Cause (three layers, all needed)

1. `run_supervisor.py` started a worker only at preparation or on a first JOIN.
2. The lab queued `START_WORKER` with dedupe key `worker:<assignment>:<device>:<recovery>`, so a second start was
   silently ignored (`INSERT OR IGNORE`).
3. The device refused a second start in the same directory ("Frozen worker assignment changed").

The handoff's workaround (remove + add) hit the same three walls for the same worker.

## Fix

A restart is a new numbered **launch**: the supervisor probes a confirmed-stopped member every 30 s while RUNNING and
starts it when its device is ON; the lab gives each launch its own command and reads only that launch's report; the
device runs it in `r<recovery>-l<launch>` and refuses while an earlier launch may be running. Never for a quarantined
worker or an unknown process state; at most 20 launches. Launch 0 keeps the old wire form. No numerical code changed.

## Receipts (CPU only)

- Tests: backend 393 passed; runtime 2583 passed, 102 skipped (same skips as before).
- `mutation.log`: 17/17 mutants killed (`mutate.py`, run on a scratch copy of `runtime/` and `backend/`).

## What this does NOT show

No device or live run yet: the fix needs a new candidate (candidate8) on every device and a live hard-stop/relaunch
receipt. Not published, deployed or pushed.
