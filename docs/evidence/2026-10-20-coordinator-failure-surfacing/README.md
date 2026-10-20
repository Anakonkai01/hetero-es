# Coordinator failure surfacing (plan step 2) — 2026-10-20

Branch `feat/v3-audit-recovery`. CPU-only: unit tests, mutation checks on scratch copies, and a Chromium check against a
throwaway fixture lab. No GPU, no SSH, no live lab, no real device was used.

## The problem

A run whose coordinator device cannot start it stays `STARTING` and the lab shows no reason. Two causes, both verified in
the code before the change:

1. `Agent.run_commands()` swallowed every `RuntimeError` (`except RuntimeError: pass`). These are the agent's own "not
   yet" messages (contribution OFF, model probe still owns the GPU, coordinator not reachable, launch ownership
   unknown, ...). The command stays unacknowledged and is retried, but nothing was recorded.
2. **Found while reading the backend (not in the plan):** the events a device agent sends (`agent_command_failed` too)
   are stored by `AgentPolling._accept_events` in the table `monitoring_events`, and **nothing ever read that table**.
   `/api/v1/events` lists only the run snapshot's events, and a `STARTING` run has no snapshot at all. So even the
   existing `agent_command_failed` event never reached the web. Changing only the severity rule (as the plan said) would
   have changed nothing a person can see.

## The change

- **Agent** (`runtime/src/heteroes/product/agent.py`): `record_failure` and the new `record_deferral` share
  `record_problem`. A deferred command is counted in its own table `command_deferrals` (so "waiting" is still not
  "failing"), stays unacknowledged and is retried exactly as before, and queues `agent_command_deferred` at attempts 1,
  10, 100, 1000 through the same outbox path. Both events carry `reason` (at most 200 characters).
  - Deviation from the plan: `reason` is sent only for the agent's own error types (`ValueError`, `RuntimeError`,
    `InvalidCommand`, exact type, as `agent.py` already does for `failureReason`), and any `scheme://...` text in it is
    replaced by `<url>`. A network or OS error can carry a grant URL or a private path, so for those only `errorType` is
    sent, as before.
  - Wire-compatible: events are generic JSON, no protocol version change. The new SQLite table is created with
    `IF NOT EXISTS`; an older agent ignores it.
- **Backend** (`backend/routes_history.py`): `/api/v1/events` now also lists the two device events from
  `monitoring_events` (only those two names: the table also holds a copy of every coordinator event, which would
  appear twice). Their ids are `<run>.m<sequence>`; coordinator events keep `<run>.e<index>`. Severity: `failed` →
  ERROR, `deferred` → WARNING (existing rules kept). The message of a device event is its `reason`.
  - Side effect to know about: the new `failed` rule also makes the coordinator events `generation_failed`,
    `scorer_failed`, `replay_failed` and `audit_execution_failed` ERROR in this API (they were INFO).
- **Web**: `describeEvent` has sentences for both events (11 known waiting reasons get their own sentence, everything
  else is shown in the agent's own words); `deviceNotice()` picks the newest event of a run if it is a device event and
  the run is `STARTING`/`RUNNING`, so the message disappears as soon as the coordinator says anything after it.
  `ExperimentDetailPage` shows it as a note with the time on every tab; the Logs tab lists it with its severity.
  Vietnamese in `packages/product-ui/src/translations.ts`.
- **Test lab**: `scripts/serve-test-lab.py --stuck-run <recorded run>` loads a `STARTING` run with one device
  deferral; `scripts/check-web-experiments.mjs` (section at the end) opens it and checks the note and the Logs row;
  `scripts/check-all.sh` passes the flag.

Untouched, as the stop rules require: `runtime/src/heteroes/v3/*`, `worker_api`, the ledger, lease/retry logic,
`backend/agent_scheduling.py` and every numerical path.

## Tests, written first (red before the change)

| Layer | New tests | Red before the change |
| --- | --- | --- |
| Agent `runtime/tests/ledger/test_device_agent.py` | deferral at attempts 1 and 10 and still unacknowledged; 100/1000 only; count survives a restart; reasons only for own errors; URL mask and 200 cut; no event without a valid assignment identity (8 cases) | 5 failed (`record_deferral` / `command_deferrals` missing, no `reason`) |
| Backend `backend/tests/test_devices.py` | device events listed per run with severity and message, two devices/two runs; severity rules and ids of coordinator events | 2 failed (events not listed, `generation_failed` was INFO) |
| Web `frontend/tests/eventText.test.mjs`, `translationsComplete.test.mjs` | sentences, tones and fallbacks; `deviceNotice` rules; every known reason has a Vietnamese sentence | import error (`deviceNotice` / `DEVICE_WAITS` did not exist) |
| Browser `scripts/check-web-experiments.mjs` | stuck run shows the note and the Logs row | with the note disabled in `ExperimentDetailPage.tsx` the check failed on a 30 s timeout; restored |

## Mutation checks (`scripts/mutation-check.py`, scratch copies, logs and mutant lists in this folder)

- Agent: `agent-mutants.json`, **21 of 21 killed** (`agent-mutation.log`). First run: 19 of 22; `assignment-id-unchecked` and
  `epoch-zero-allowed` showed a missing test (added), `empty-reason-is-a-string` was dead code (`or None` removed).
- Backend: `backend-mutants.json`, **15 of 16 killed** (`backend-mutation.log`), run on the two new tests only (two
  older tests in `test_devices.py` need artifacts outside the scratch copy). First run: 13 of 16; the rules for
  `unknown` and the `<run>.e<n>` id format showed missing assertions (added). The survivor is
  **`unordered-device-events`** (dropping `ORDER BY m.sequence`): equivalent in practice, because SQLite returns these
  rows in insertion order anyway and the final list is sorted by timestamp. The clause stays so the order is defined.
- Web: `frontend-mutants.json`, **16 of 16 killed** (`frontend-mutation.log`). First run: 15 of 16; the tone of a failure
  without a reason was not asserted (added).

## Checks

`scripts/check-all.sh docs/evidence/2026-10-20-candidate5-checks/checks`, run alone: **ALL PASS** (runtime 2482 passed /
102 skipped, backend 374 passed, frontend 88, worker 87, i18n 0 missing). Details and screenshot in
`../2026-10-20-candidate5-checks/README.md`.

## What this does NOT show

- It does not reproduce the stuck candidate3 run on real machines, and it was not tried on Windows or with a GPU. The
  agent behavior is shown with unit tests and the web behavior on a fixture lab whose device event was inserted by the
  fixture, not sent by a real agent. The agent-to-server step is covered by the existing backend event-acceptance
  tests plus the new listing tests, not by one end-to-end run.
- The reason is only as good as the agent's message: a state that never raises `RuntimeError` (for example a coordinator
  that starts and then dies silently) is still not explained by this change.
- First report is immediate (attempt 1), later ones come at attempts 10, 100 and 1000, so with a 10 s heartbeat the
  message is refreshed after about 100 s, 17 minutes and 3 hours. The note shows the time of the last report.
- A lab running an older backend stores the new events but does not list them; an older agent sends no deferral events.
  Nothing was deployed: the public lab is untouched and still at its old commit.
- No numerical, ledger, lease or retry behavior was changed or re-verified here.
