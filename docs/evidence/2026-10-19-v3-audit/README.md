# Recipe v3 deterministic text audits — 2026-10-19

Code commit: `aebe64e`, on `feat/v3-audit-recovery`. No protected numerical,
ledger, generation-record or worker-API file changed. No live device state changed.

## Result

The coordinator deterministically samples the default 1/20 of candidate-ID SHA-256
space, leases committed candidates to a different admitted worker, authenticates
its operational lease and commits the returned text hash through Ledger.record_audit.
Completed audits survive restart; operational leases expire/retry independently.
Audits are drained before the update changes parent/context. Cancellation stops
new audits; lack of a second worker or audit timeout emits audit_incomplete.
Neither mismatches nor infrastructure errors rewrite committed rewards.

At three mismatches the existing ledger quarantines both workers. The worker job,
authenticated current-coordinator events and UI carry this decision. The backend
only targets workers selected in that assignment, does not overwrite REVOKED, and
does not reapply duplicate events after an administrator's later decision. Exact
restore failure is fatal and retained separately without manufacturing a completed
audit or altering the committed attempt.

- `check-all.log`: **22/22 ALL PASS**, completed before this evidence was committed.
  Ran in detached `/home/pc5070ti/projects/heteroes-v3-audit-check` at `aebe64e`.
- `checks/runtime-tests.log`: **2,262 passed, 100 skipped**.
- `checks/backend-tests.log`: **301 passed**.
- `audit-final-targeted.log`: 17 passed, including two real CPU workers over HTTP,
  all 8 candidates force-audited and independently re-scored/replayed.
- `mutation.log`: **8/8** runtime mutants killed. `backend-mutation-second.log`:
  **2/2** backend mutants killed. No equivalent survivors.
- Web types/lint, UI event rendering, i18n, browser and Electron fixture probes pass
  in check-all. Mismatch/quarantine UI semantics have unit checks.

## Intermediate receipts

Tests-first logs preserve expected missing/new-behavior failures. The first backend
mutation invocation copied a nonexistent root tests directory; it did not execute a
control or mutant. The second invocation corrected the copy list and passed.
The first check-all was intentionally interrupted in runtime-tests because its
shell used the primary checkout instead of the new detached checkout; no source
had changed during it. `checks-interrupted/` and `check-all-interrupted.log` retain
that incomplete run. The authoritative check-all was restarted in the detached
checkout and finished with all 22 checks. Other targeted UI/format/import failures
were repaired before the final run; their logs are retained.

## What this does NOT show

CPU fixture acceptance only: no real-model GPU result, Windows or installer
acceptance, deployed lab, networked multi-machine run, or learning benefit.
The 5% rule is deterministic sampling, not guaranteed coverage for every small
run. Single-worker runs report incomplete audits. A mismatching pair is evidence
of inconsistency, not proof identifying which worker is at fault. Operational
leases are intentionally reissued after restart; committed audit rows are retained.
