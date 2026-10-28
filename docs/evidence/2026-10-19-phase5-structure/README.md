# Phase 5 — structural readability before automatic formatting

Baseline: `8c66ca5`. Authentication, inventory, experiments, history, account management, workspaces and operations
have separate APIRouter modules. Static web/manifest installation preserves its original order. Request contracts and
validation are separate from the app factory. Device contracts, scheduling, commands and poll reconciliation have
separate modules; poll calls ordered observation, boot, quarantine, event and report steps within the original transaction.
Every backend CREATE TABLE now lives in `migrations.py`; existing schema guards, table names and call order are retained.
No management schema version or numerical ledger migration is introduced.

Dense experiment, workspace/fleet, Operations and Worker views are split into components/hooks. The Worker separates
bridge state/actions, contract types, messages and compute settings. 310 unused Vietnamese translation keys were removed
(1,621 → 1,311); the checker now also rejects unused keys using exact strings from active UI tables and backend statuses.
Expected background recovery/metadata failures log only their exception type. Existing security/policy findings are
recorded in `docs/SECURITY-NOTES.md`, without changing their behavior. Redundant `if True` and nested re imports are gone.

`backend-final.log`: 283 passed (one new poll-choice regression). `runtime.log`: 2,110 passed, 100 skipped.
`ui-unit.log`: 79 passed. `check-all.log` and `checks/` record the full CPU product suite; its backend run preceded the
additional regression and counted 282. Final backend verification includes that new case. Intermediate import/indentation
failures from extraction are retained in the earlier logs; the final runs follow their corrections.

`mutation.log` initially found a surviving desired-contribution mutant. The missing ON/OFF poll-response assertion was
added to `test_devices.py`. `mutation-final.log` then kills 2/2 poll/event mutants after a passing control.
`i18n-mutation.log` kills 2/2 missing/unused translation mutants. Numerical production sources remain unchanged.
`lint-preparation.log` records eight safe import/f-string style fixes in tools/tests, before the format-only commit.
Formatting configuration and `check-python-ast.py` are prepared here so the next commit can prove AST equality.

## What this does NOT show

No GPU computation, native Windows execution, live deployment or new installer. Fixture browser/Electron probes do not
show real distributed GPU work. The retained ledger and runtime agent were not split merely for file-size targets.
Automatic formatting and its separate AST proof follow in the next commit.
