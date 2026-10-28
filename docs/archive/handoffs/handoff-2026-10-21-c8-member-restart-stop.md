# Candidate8 final acceptance run: parity exact, but members are NOT restarted on real machines — STOP for a stronger model

Checkpoint 2026-10-21 ~15:25 +07, branch `feat/r11-scheduling-elastic`, local only (**not pushed**). Supersedes
`handoff-2026-10-21-member-restart-candidate8-next.md`. No subagents (owner rule). Stop rule used: the member-restart fix
`98dd705` did not restart anyone on the real machines (Windows 10-minute rule), so Sonnet stopped and did not patch.

## Done

- CPU gate 23/23 ALL PASS on the source (`evidence/2026-10-21-r11-candidate8-checks/`). Build `lf1-20261021-r11-candidate8`,
  prepared (not published), 105 + 182 source files byte-equal, source-copy + packaged Linux Server/Worker PASS
  (Worker on the second try after the known cold-launch timeout) (`evidence/2026-10-21-r11-candidate8/`).
- Installed + self-test PASS on the isolated lab, 5070, Thao Windows, Thao WSL CPU coordinator, 1660S and **Quang** (first
  time); installed sources equal the repo (`evidence/2026-10-21-candidate8-device-upgrades/`). One operator slip, recorded: a
  GPU self-test on the CPU coordinator home, redone with `--device cpu`.
- Run `a78af4b3a724414a82f2589d7d4f8604` COMPLETED 50/50, 400 results, 13 audits 0 mismatch, parity `ALL EQUAL` on the
  5070, two explicit expiries (Windows hard stop g16, 5070 SIGSTOP g43 → stale result not committed), 1660S JOIN/LEAVE/JOIN
  in the ledger (`evidence/2026-10-21-long-multimachine-run-candidate8/RESULTS.md`).
- New operator tools: `operator/monitor.py` (8 tests, 21/21 mutants), `worker_proc.py` (kill/SIGSTOP one `run_worker.py` by pid
  + start time), `elastic_checks.py` + `negative.py` (positive + 9 tampered ledgers).

## What failed (read RESULTS.md)

1. **Thao Windows never restarted** after the whole-app hard stop, relaunch and contribution ON. No `worker_restarted`, no
   `START_WORKER launch 1` in `device_commands`. The Windows app's Electron main kept spawning a new `desktop_bridge`
   every ~10 s from 14:53 (new `bootId` each time ⇒ contribution OFF again). Hypothesis (unproven): `startAgent` always PATCHes
   `/api/v1/device/qualification`; `backend/devices.py:354` returns 409 while the device is reserved by the running
   experiment, so a freshly started app can never stay up. Candidate7 showed the same symptom, so the fix may never have been
   exercised. The loop is only logged when `status` is polled (`service.cjs:recordAgentFailure`).
2. **1660S rejoined (g44) but was never started again** although it is a CLI agent that stayed up and ON. The supervisor's
   `_restart_members` swallows every probe error silently; the reason is unknown. Compare `backend/agent_commands.py` probe
   (`target.enabled and target.desired`, device seen < 30 s) and `agent_scheduling.release_left_members` (GPU released on
   LEAVE).
3. **Quang `kill -9` was not exercised** (gate chain too slow: Windows verdict at g41 > last start g39). The Linux CLI restart
   path is therefore still untested on hardware. Suggest running it alone, early, on a quiet lab.

## Next, for a stronger model

1. Prove or kill the 409 hypothesis: reproduce on a scratch lab with a reserved device and a restarted app (log the PATCH
   status; call `status` to trigger `recordAgentFailure`). Decide the fix (skip the PATCH when the self-test is unchanged,
   or allow an identical qualification while reserved; do not `quit` the child on a qualification failure).
2. Find why `_restart_members` did not start the 1660S: make probe failures leave a lifecycle event
   (`worker_restart_deferred` with the HTTP status) so it is observable, then fix.
3. Rebuild (candidate9), then a SHORT focused run: Quang `kill -9` first (g8), then 1660S leave and rejoin, then Windows whole-app
   hard stop, one fault at a time with its own deadline; keep SIGSTOP (it passed). Reuse `evidence/…-run-candidate8/` tools
   (copy; do not edit this folder).
4. Only then `plan-r11-release.md` steps 6–8 (FF main, push, flag day with "đồng ý" for each irreversible step).

## Current state

- All devices contribution OFF. Windows app **quit** (offline). Lab (8790) and 5070 desktop worker run candidate8; installer HTTP
  8802 serves the candidate8 directory. Agents `heteroes-worker run` idle on Quang (pid in `/tmp/heteroes-r11-c8/agent.pid`)
  and the 1660S. Thao WSL CPU coordinator agent exited with the run.
- Not published, deployed, merged or pushed. c7 run stays unverified (owner skipped it).

## Retained, unexplained

- First packaged Worker check timed out at `electron.launch` (30 s) from the Archive volume; rerun passed (also seen with c7).
- Why the Windows bridge died at ~14:53 the first time; whether c7's relaunch was the same loop.
- Items in `handoff-2026-10-21-scheduling-elastic.md` ("Retained, unexplained") still stand.
