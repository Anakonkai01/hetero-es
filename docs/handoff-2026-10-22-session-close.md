# 2026-10-22 ~15:30: session closed — tier 3 running, midterm demo done, finding 10 fix waits for tier 3's end

Branch **`feat/gsm8k-demo`** (not pushed). Lab on `a198cb0` (branch `deploy/candidate13` = candidate12 + `b5e1bc7`).
Details of the morning: [handoff-2026-10-22-tier3-running.md](handoff-2026-10-22-tier3-running.md). Results:
`docs/evidence/2026-10-22-gsm8k-demo/RESULTS.md` (tiers 2e and 3, findings 9 and 10).

## State at 15:22

- **Tier 3** `fa67c66c203a4afaaaad9f9215656e4d` RUNNING, generation 65/300, 2,080 results (5070ti-nhut 898, 5070ti-nhan
  794, 3060-thao 370, 1660s 18), 101/101 audits matched, no quarantine, ~4.8 min per generation → ends about
  **2026-10-23 10:00–11:00**. Validation (500 rows): base 0.608, gen 25 0.606, gen 50 **0.572** (a drop of ~1.6 SE;
  the lab keeps the base as best so far; learning is exploratory, not the claim).
- 1660S flaps (hardware): lost 10:19, back 11:01, lost 11:16, rebooted itself ~13:04 and came back (launch 2). Each
  return needed no hand action.
- Running in background on 5070ti-nhan: `.scratch/gsm8k-demo/watch.py tier3 60` (lab-based: its `done`/marks are empty
  now, finding 10) and the 10-hourly lab sign-in loop (`tier3-relogin.out`; started from this session's scratchpad).
  **Read progress from the ledger**, not the lab: `~/.local/share/heteroes-worker/agent-state/runs/fa67c66c…/ledger.sqlite`
  (`generation_update`, `result`, `audit`), `validation-*.json`, `lifecycle.jsonl`.

## Done this session (commits `cd4ab94` … this one)

- (b2) fix deployed on the lab (09:12) and accepted by tier 2e (finding 9: a re-add logs `worker_restarted`).
- Tier 3 launched 10:01.
- Midterm notebook (`7c48403`): offline-capable, tiers 2b–2e section, tier 3 snapshot at gen 25; executed copy, HTML,
  videos, replay pages in `.scratch/gsm8k-demo/midterm/` and `/mnt/Archive-2tb/heteroes-local/midterm-demo-20261022/`;
  `tier3-now.mp4`/`-replay.html` drawn from the ledger at gen 46 (`heteroes.demo.ledger_view`).
- **Finding 10** (the lab timeline/web live view of a long run lost every attempt): fixed in `94225d2`
  (`bounded_snapshot` keeps the newest generations whole), runtime suite 2608 passed, mutation 5/5. **Not deployed.**

## Next session, in order

1. **When tier 3 is COMPLETED** (not before: updating 5070ti-nhan restarts the coordinator; `systemctl stop` = contribution
   OFF + drain, which would end the run; a `kill -9` recovery was offered and the owner chose to wait): results into
   RESULTS.md (final state, validations, selected checkpoint, the one test evaluation, member story, parity: ledger
   replay + regenerate every audited candidate and one generation with `verify_managed_run.py`, 4th argument = run id),
   final `snapshot.py tier3 tier3` + `media.py tier3 --video` (use `ledger_view` for the timeline, the lab's is empty).
2. **Build candidate13** = `feat/gsm8k-demo` (wave 2 + `b5e1bc7` + finding 10 fix) and deploy: lab (`deploy-lab-c12.sh`
   pattern, idle lab) and the three Linux agents (`update-to-c12.sh` pattern). Then a short `evalChunks: [16, 32, 64]` run
   (ADR-010) and check the web live view on it.
3. **SDK → lab bridge** + "you are the researcher" notebook section: [plan-sdk-lab-bridge.md](plan-sdk-lab-bridge.md);
   grill the owner on the API first.
4. Finding 9 product fix (timeline shows a re-added member); Windows app update on 3060-thao (someone at the screen);
   disk: finished runs keep 4–6 GB of weights each under `~/.local/share/heteroes-worker/artifacts/coordinators/` (~33 GB),
   prunable after their parity receipts, with the owner's OK.
5. An old candidate9 server under xvfb (started ~2026-10-21 16:00 from `.scratch/isolated-lab`) is still running on
   5070ti-nhan; not started by this session, left alone.
