# Handoff — plan step 1 done, step 2 (surface coordinator agent failures) next (2026-10-20, Claude Sonnet 5.5)

Read `../AGENTS.md`, `plan-r11-release.md` (the owner's plan; steps 2–8 are still open), then this file. The owner asked
that code-heavy work go to a stronger model / higher effort (xhigh) or Codex, so this session stopped after step 1.

Branch `feat/v3-audit-recovery`. HEAD after this handoff is the commit that adds it (parent `ad3f192`). `main` is still
at its old commit and has not been fast-forwarded.

## Done: step 1 (backup + push)

- Plan copied to `docs/plan-r11-release.md` (b4a34fb). Secret scan of all history: clean (details in
  `docs/evidence/2026-10-20-backup/README.md`).
- `origin` = `git@github.com:Anakonkai01/hetero-es.git` added; `git push origin --all` created all 38 local branches
  (42 refs now on the remote). Pushed content: everything up to b4a34fb. Owner said pushing is fine despite the
  internal Tailscale IP in evidence.
- Offline bundle on Archive (UUID 10443D1F443D094C): `/mnt/Archive-2tb/heteroes-local/backups/heteroes-2026-10-20.bundle`,
  verify OK, sha256 `9b92445…f3b` (full value in the evidence README).
- AGENTS.md rule updated (ad3f192): push + fast-forward merge to `main` authorized; no force, no remote branch delete, no tags.

## Open from step 1 (first thing to do)

1. `git push origin --all` for the commits made after the first push (ad3f192 and this handoff). The tool permission
   layer blocked a second push and a `git ls-remote` in this session; the owner may need to run `! git push origin --all`
   or allow the Bash rule.
2. After that, compare every local branch tip against `git ls-remote origin` and record it in the backup README
   (append a dated note; do not rewrite the earlier text).

## Step 2 — verified code facts (do not trust line numbers blindly, re-grep)

- `runtime/src/heteroes/product/agent.py` `run_commands()` (~line 536): `except RuntimeError: pass` swallows the agent's
  own "not yet" deferrals (contribution OFF, model probe GPU release, coordinator launch ownership unknown,
  coordinator not reachable, `run_supervisor.py` ~109). Nothing is recorded, so a STARTING run shows no reason.
- `record_failure()` (~line 553) already counts into the `command_failures` table (`id, kind, error_type, attempts,
  last_at`) and queues an `agent_command_failed` event into `event_outbox` at attempts 1/10/100/1000, only for commands
  with a valid 32-hex `assignmentId` and int `epoch >= 1`. Events are generic JSON, so adding fields needs no protocol
  version change. The outbox row id is `sha256(assignment + encoded)`; `INSERT OR IGNORE` makes it idempotent.
- `backend/routes_history.py` `event_list()` (~line 46): severity = ERROR if `"error"` in the event name, WARNING if
  `"unavailable"`/`"unknown"`, else INFO. `agent_command_failed` therefore shows as INFO. Message is `event.get("error",
  event name)`, so a `reason`/`error` field must be present to be useful.
- Existing tests next to this code: `runtime/tests/ledger/test_device_agent.py` (agent); look for the backend history
  route test with `grep -rn "event_list\|/api/v1/events" backend/tests`; frontend experiment detail: find where events/
  status render under `frontend/src` (reuse existing alert/event components and i18n key pattern; add keys to every locale).

## Step 2 — wanted change (from the plan, small and wire-compatible)

- Agent: for `RuntimeError`, increment a separate counter and queue `agent_command_deferred` with `kind`, `reason`
  (`str(error)[:200]`) and `attempts` at attempts 1/10/100/1000, through the same outbox path as `record_failure`
  (refactor the shared part rather than copy it). The command stays unacknowledged and is retried exactly as before.
  `agent_command_failed` additionally carries `reason = str(error)[:200]`.
- Backend: `agent_command_failed` → ERROR, `agent_command_deferred` → WARNING (keep existing rules).
- Web: on the experiment detail of a STARTING/RUNNING run, show the latest `agent_command_failed`/`agent_command_deferred`
  reason (i18n in every locale).
- Tests first and failing before the change: agent (RuntimeError → exactly one deferred event at attempt 1, none at 2,
  again at 10, command still unacknowledged), backend severity, frontend unit test. Mutation check on a scratch copy
  (`scripts/mutation-check.py`), every survivor gets a test or a documented equivalence. Evidence
  `docs/evidence/<date>-coordinator-failure-surfacing/` with **What this does NOT show**. Then `scripts/check-all.sh
  docs/evidence/<date>-candidate5-checks/checks` must be ALL PASS and run alone.
- Stop rule from the plan: if the fix needs changes in `runtime/src/heteroes/v3/{distributed,audit,recovery,run}.py`,
  worker_api, ledger use, lease/retry logic, `backend/agent_scheduling.py` release logic or any numerical path, stop and
  hand off again. The planned change touches none of them.

## Then, in order (unchanged from the plan)

3. Build r11 candidate5 (follow `docs/evidence/2026-10-20-r11-candidate4/README.md`). 4. Upgrade the isolated lab and
devices (owner must first free Quang's Windows C: to ≥ 20 GB; it had 6.9 GB). 5. Long managed run, 3 GPU workers, 50
generations, audits, induced Quang failure, independent re-execution parity. 6. Merge `main` (ff only) and push.
7. Flag day with the owner present and an explicit "đồng ý" before each irreversible step. 8. Docs and close.

## Live state (unchanged this session)

Public lab untouched. All test devices off; the isolated lab is stopped. No SSH, GPU or lab operation was used here.

Resume prompt:

> Đọc AGENTS.md, docs/handoff-2026-10-20-step2-failure-surfacing.md và docs/plan-r11-release.md, hoàn tất mục "Open from
> step 1", rồi làm bước 2 của plan. Tuân thủ các luật dừng. Nói chuyện với tôi bằng tiếng Việt.
