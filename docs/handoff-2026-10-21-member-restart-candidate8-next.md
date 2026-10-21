# Member restart fixed (CPU); next = plan + run the FINAL acceptance on candidate8

Checkpoint 2026-10-21 ~14:00 +07, branch `feat/r11-scheduling-elastic`, local only (**not pushed**). Supersedes
`handoff-2026-10-21-candidate7-acceptance.md` where they differ. No subagents (owner rule).

## Done this session

- **Fix `98dd705`** (owner: "sửa luôn"): a member whose worker stopped while the run goes on is started again
  (ADR-009 item 8, receipts `evidence/2026-10-21-member-restart/`). Cause was in three layers: supervisor only started
  at preparation/first JOIN; lab deduplicated a second `START_WORKER` away; device refused a second start in the same
  directory. So the old "remove + add" workaround did not work either. A restart is now a numbered `launch` (own lab
  command, own process report, own device directory `r<recovery>-l<launch>`, fenced on the old process being confirmed
  stopped; probe every 30 s; max 20; never quarantined/unknown). Launch 0 keeps the old wire form. No numerical change.
  Tests: backend 393, runtime 2583 passed (102 skipped as before); mutation 17/17 killed.
- **c7 run verification, started (not finished):** private ledger copy collected from Thao WSL (COMPLETED, no grants):
  `.scratch/r11-c7-verify/private-run-copy/`, summary `collect-summary.json` (50 applied, 400 results, 401 attempts,
  9 audits 0 mismatch, 1660S JOIN g11 / LEAVE g31, one expiry `g19/c3` attempt 1).
- **Quang online** (2026-10-21 13:11): SSH works, C: 20 GB free, no HeteroES process running. Still candidate6.

## Running in the background when the session closed (check their output first)

1. GPU verifier → `docs/evidence/2026-10-21-long-multimachine-run-candidate7/parity.json`, log
   `.scratch/r11-c7-verify/verify-managed.log` (last line `exit=0` when done). If missing/killed, rerun (command in
   that log's folder history: `verify_managed_run.py <private-run-copy> <HF snapshot 7ae5576…> reward.py <run> parity.json --device cuda`
   from `runtime/` with `PYTHONPATH=src`).
2. CPU gate `scripts/check-all.sh docs/evidence/2026-10-21-member-restart/checks` → `.scratch/r11-c7-verify/check-all.out`
   (16 PASS, 0 FAIL at close). If it was killed, delete the partial `checks/` folder and rerun.

## Next session, in order

1. Finish c7 verification: `verify-records.py … --joiner cli-3e355c6e9e70 --failed-worker desktop-9f9da13f0f82`, then
   `.scratch/r11-c7-verify/negative.sh` (two tampered scratch ledgers: a g5 result given to the 1660S, and no expiry row;
   both must FAIL). Usage receipt, screenshot (`.scratch/r11-long-run2/browse.mjs`), RESULTS.md + SHA256SUMS. Commit.
   This stays secondary evidence.
2. **Owner decision (2026-10-21): the final acceptance is a full 50-generation run on candidate8**, the bytes that will
   be published. Owner wants a **detailed plan first** (grill before plan: ask questions, explain from basics). Proposed
   content: Quang joins for the first time; 1660S JOIN ~g10 / LEAVE ~g30; hard-stop Thao Windows ~g20 and relaunch;
   **new requirement: it is restarted automatically** (`worker_restarted` in lifecycle, launch 1, results committed after
   the relaunch) with no manual add. Predeclare in a new evidence folder before running.
3. Build candidate8 like candidate7 (`evidence/2026-10-21-r11-candidate7/README.md`: build-apps.sh into a fresh Archive
   dir, prepare-only, source byte comparison, source-copy + packaged Linux checks), then install on 5070, Thao Windows,
   Thao WSL CPU coordinator, 1660S, **Quang**; self-tests.
4. Run, verify the same way, then `plan-r11-release.md` steps 6–8 (merge/push, flag day with "đồng ý" for every
   irreversible step, docs).

## Current state

- Isolated lab (8790), 5070 desktop worker, private installer HTTP (8802) still running candidate7. Contribution OFF on
  all devices. 1660S agent and Thao Windows app still running (candidate7).

## Retained, unexplained

Unchanged from `handoff-2026-10-21-candidate7-acceptance.md`.
