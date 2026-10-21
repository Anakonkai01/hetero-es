# Candidate9 restart run done: 2 of 3 restarts recovered, the 1660S verdict `failed` (STOP rule), parity exact. Needs a decision.

Checkpoint 2026-10-21 ~19:25 +07, branch `feat/r11-scheduling-elastic`, local only (**not pushed**). Supersedes
`handoff-2026-10-21-candidate9-restart-run.md`. Result and evidence: `evidence/2026-10-21-restart-run-candidate9/RESULTS.md`.

## Where it stands

- The two fixes of `f21cc1f` worked on real machines: **Quang `kill -9` recovered; Thao Windows whole-app hard stop recovered**
  (one `worker_restart_deferred` 409, then `worker_restarted` and 30 new results). The c8 Windows loop is gone.
- The 1660S leave/rejoin verdict is `failed`: restarted by the system and alive (12 audits), but no main candidate lease in its second
  window, so no new committed result. Likely cause: scheduler `greedy-tail` gives main work to faster GPUs (also 1 commit in c8).
  **Unproven.** By the predeclared stop rule c9 is not accepted; I did not patch anything.
- Run itself: 50/50, 400 results, 23 audits, 0 mismatches, independent 5070 regeneration ALL EQUAL.

## Decisions for the owner / a stronger model

1. Is "a new committed result" the right restart criterion for a slow member under `greedy-tail`? Options: (a) accept a restarted
   member's audit or heartbeat as proof of restart for slow members and declare the criterion met without a new run;
   (b) rerun only event 3 with a criterion that can be met (e.g. a scheduler that guarantees a slow member one candidate, or check
   restart through `worker_restarted` + a step with work kind AUDITED/COMMITTED); (c) change scheduling. Do not change a criterion
   after seeing the result without the owner saying so.
2. If accepted, `plan-r11-release.md` steps 6-8 (Windows uninstall, FF main + push, flag day), each irreversible step with "đồng ý".

## Device state

Isolated lab 8790 and installer HTTP 8802 run c9. 5070 desktop app, Quang and 1660S agents are up and contribution OFF; Thao CPU
coordinator offer exited; Windows app quit (offline). All receipts are committed. Nothing published or pushed.

## Retained

- Electron cold-launch 30 s timeout (hit again on the 5070).
- Windows `launch` driver reports "Execution context was destroyed" and its wrapper hangs, though the app starts (the monitor's
  `relaunch` does not wait for it).
- Quang kill helper exits 1 with `"gone": false` although the kill works.
- Negative controls cannot pass their positive case on a ledger where the joiner has no commit in a window (c8 and c9 ledgers).
