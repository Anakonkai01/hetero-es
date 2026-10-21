# Candidate8 final acceptance: NOT ACCEPTED (stop rule), parity and most elastic checks hold

Run `a78af4b3a724414a82f2589d7d4f8604`, 2026-10-21 ~14:33-15:03 +07, build `lf1-20261021-r11-candidate8`, declared in
`README.md` (committed before the run). Verdict: **the member-restart fix did NOT work on the real machines, so the final
acceptance is not passed**. The run itself completed and its numbers are exact.

## What held

- **COMPLETED, 50 applied generations, 400 committed results** (402 attempts: 2 expired). 13 audits, **0 mismatches**, no
  quarantine (`collect-summary.json`). Commits: 5070 216, Quang 138, Windows 45, 1660S 1.
- **Independent 5070 Ti regeneration, separate cache** (`parity.json`): `ALL EQUAL`, 50 generations; every candidate text, hash and
  reward, every context and record, all 50 child hashes. `records.json`: contexts and records of all 50 generations equal,
  `membershipViolations == []`, 400 rows = 400 distinct candidates.
- **Two real expiries, explicit rows, each committed by a later attempt (Quang, attempt 2):**
  Windows `g16/c6` (hard stop of the whole app at g16 while it held the lease, `operator-events.jsonl`) and the 5070 `g43/c0`
  (SIGSTOP of its `run_worker.py` for 183 s, then SIGCONT).
- **Event 6 (stale result): accepted outcome (a).** After SIGCONT no second result for `g43/c0` appears: attempts 402 = 400
  committed + 2 expired, no committed result after its own attempt's deadline (0 rows).
- Elastic membership in the ledger: 1660S JOIN g11, LEAVE g42, JOIN g44; no committed result by a non-member.
- Usage (`usage-summary.json`), browser screenshot without page errors (`experiment-detail.png`).
- Controls: `negative-controls.log` (a positive control and nine tampered copies of the candidate7 ledger, each failing for
  its own reason) behave as declared.

## What did NOT hold (declared checks, `records.json` → `ok: false`)

1. **Event 2: Thao Windows was never started again.** After the relaunch (g16 + 247 s) and contribution ON, no
   `worker_restarted` and no `START_WORKER launch 1` command exists (`device_commands`: only the first START at 14:33). The
   monitor recorded `restart_verdict: failed` at 600 s. Windows made 45 results, none after g16. The workaround remove+add was
   not used.
2. **Event 4 (Quang `kill -9`) was not exercised** (`not_exercised`): the cooperation gate waited for the Windows verdict,
   which came at g41, after the last start generation (g39).
3. **Event 5: the 1660S joined again (g44) but was never started again** (no `worker_restarted` for `cli-3e355c6e9e70`, no
   worker directory `-l1`), so the second window has no result. Its only result is g15 (first window).
4. `README.md` asked for a result in each of the 1660S windows: the second one has none.

## Operator interventions, all recorded in `operator-events.jsonl`

- Contribution was turned ON again once for the Windows device (`manual_contribution_on_second_boot`, 14:53:41), because
  its `bootId` had changed and contribution is per boot. That is the declared operator step. It did not produce a restart.
- After the run: contribution OFF everywhere; the Windows app was quit (see below).
- The monitor's restart deadline ran from the FIRST contribution ON (14:45:31); the manual ON came ~8 min later, 1.5 min
  before the deadline. No other manual action touched membership or workers.

## What was observed on the Windows device (no fix tried)

From 14:53 on, the Electron main process (`HeteroES Worker.exe`, started 14:45:23) spawned a new `heteroes.product.desktop_bridge`
child roughly every 10 s; each child lived about 10 s, so the lab saw a new `bootId` each time and contribution (per boot)
was OFF again. `worker.log` shows nothing after 14:45, because the agent failure is only logged when `status` is polled
(`service.cjs:recordAgentFailure`). After the run ended and the app was quit, `DEVICE_QUALIFICATION_UPDATED` succeeded at
15:03:54.

**Hypothesis (not proven):** `startAgent` (`desktop/worker/electron/service.cjs`) always sends
`PATCH /api/v1/device/qualification`; the lab (`backend/devices.py:354`) answers 409 while the device is enabled, desired, or
**reserved** (`has_device_reservation`). While the experiment holds the GPU reservation, a freshly started app instance
can never qualify, `startAgent` throws, quits the child, and tries again, so it never stays online with contribution ON. A
member whose WHOLE app was killed therefore cannot come back during the run. Candidate7's relaunch looked the same
("ONLINE and ON, kept `alive: False`"), so the member-restart fix (98dd705) may never have been reached on this path.

The 1660S case (CLI agent, never killed, contribution ON, device online) has no such explanation and needs its own look:
`_restart_members` swallows every probe exception, so the supervisor leaves no trace of why it did not start the member.

## What this does NOT show

The run is not an acceptance of candidate8, not a release pass, and no learning, speedup or universal cross-GPU claim. The
Linux CLI restart path (Quang kill) was not exercised. Candidate7 stays unverified. No publication, deployment, merge or push.
