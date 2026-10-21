# Candidate9 restart run: NOT ACCEPTED by its own stop rule (one verdict `failed`), 2 of 3 restarts recovered, parity exact

2026-10-21 Asia/Ho_Chi_Minh, experiment `dd760b241c46405ab2fbdc0bafb8612a`, build `lf1-20261021-r11-candidate9`. Run as predeclared in
`README.md` (committed before the run). Devices: `../2026-10-21-candidate9-device-upgrades/`. Nothing was repaired by hand.

## Result

- COMPLETED, **50 applied generations, 400 committed results (400 distinct candidates), 23 audits, 0 audit mismatches, no quarantine**
  (`collect-summary.json`). Commits: 5070 178, Windows 113, Quang 108, 1660S 1 (`usage-summary.json`).
- **Independent 5070 Ti regeneration** (`parity.json`): `ALL EQUAL`, 50 generations (candidate texts, text hashes, rewards).
  `verify-records.py` (`records.json`): all 50 contexts, update records and record hashes equal.
- Restart verdicts (`operator-events.jsonl`):

| # | Fault | Verdict | Evidence |
| - | ----- | ------- | -------- |
| 2 | `kill -9` of Quang's `run_worker.py` (g5, held a lease) | **recovered** | `worker_restarted` (launch 1) in the coordinator `lifecycle.jsonl`; 97 Quang results committed after it; one `expiry` row for the killed attempt, retried by attempt 2 |
| 3 | 1660S LEAVE (eff. g7), JOIN again (eff. g8) | **failed** | `worker_restarted` (launch 1) was logged, the agent was alive and did **12 audits** after it, but it was given **no main candidate lease** in its second window. In the whole run it has one main result (g5, first window). The verdict rule requires a new committed result within 10 minutes |
| 4 | Hard stop of the whole Thao Windows app (g30, held a lease), relaunch after 244 s | **recovered** | one `worker_restart_deferred` (HTTP 409, lab still counted the old boot), then `worker_restarted` ~32 s later; 30 Windows results committed after it; one `expiry` row, retried by attempt 2. The app stayed up with one boot |

- Elastic checks (`records.json`): `membershipViolations = []`; 1660S changes JOIN(3), LEAVE(7), JOIN(8) exactly as declared;
  expiry rows for Quang and Windows with each candidate committed by a later attempt; restart checks `ok` for Quang and Windows
  with no manual membership change; 400 rows. The overall `elastic.ok` is **false** only because the 1660S has no committed result
  in its second window (`joinerCommitGenerations = [5]`).

## What the 1660S facts say, and what they do not

The system restarted the 1660S's worker by itself and the 1660S kept working (audits at g16, 18, 26, 27, 31, 33, 35, 38, 45-48).
It never received main work in window 2. Scheduler `greedy-tail` gave candidates to the faster machines; the same happened in
candidate8 (1 commit). This looks like scheduling, not a restart failure, but **that is a hypothesis, not proven** here. The
declared criterion (a new committed result) was not met, so by the stop rule the candidate is not accepted. Whether the criterion
or the scheduler should change is a decision for the owner or a stronger-model session; I did not change either.

## Operator notes and deviations

- The monitor logged one `monitor_error` at the Quang kill: the remote `worker_proc.py kill` printed its receipt but exited 1
  (`"gone": false`, the process was still dying when it checked). The kill took effect (`worker_restarted` followed); the monitor continued.
- Contribution was turned ON for the four GPU devices and the Thao CPU coordinator before the offer, and OFF for all after COMPLETED.
  The Windows app was quit after the run (0 processes). The 5070 desktop app, the Quang and 1660S agents are still running, OFF.
- The private run copy needed `dataset.json` and the three split files; they are not in the Thao run folder, so they were copied from
  the candidate8 copy (identical `rows.json` and seeds; the verifier checks content and split hashes against the recipe, and passed).
- **Negative controls.** On this run's ledger the positive control cannot pass (`negative-controls.log`: 1 WRONG) because the 1660S has no
  commit in its second window, which the checker requires; the same holds on the candidate8 ledger
  (`negative-controls-on-c8-ledger.log`). On the candidate7 ledger (1660S committed inside both windows) all ten controls behave
  (`negative-controls-on-c7-ledger.log`, as in candidate8's receipt).
- Browser screenshot of the experiment page (`experiment-detail.png/.txt`): COMPLETED, 23/23 audits, 0 mismatches, no page errors.

## What this does NOT show

One configuration of five machines, one occurrence of each fault. No claim about learning, speed, arbitrary models or universal
cross-GPU equality. No coordinator or lab crash test, no stale-result recheck, no publication, deployment, merge or push.
The release flag day (`plan-r11-release.md` steps 6-8) is NOT started and needs the owner's explicit "đồng ý" at each step.
