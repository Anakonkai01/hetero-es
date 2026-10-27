# D10 one automatic restore recovery per worker and run (M2), 2026-10-27

The ledger quarantine is frozen (never lifted), so a recovered worker returns as `<worker>~r1`
(`heteroes/restore_recovery.py`). Worker: budget spent first and persisted; reload base weights in place from the
verified model files (`v3.model.reload_base_`), take the canonical parent (`sync`), perturb/restore self-test
(`CandidateExecutor.selftest_restore`), then ask for work as the alias. A failed recovery is recorded as terminal.
Coordinator (`CoordinatorRecoveries`, `<run>/restore-recoveries.json`): admits the alias only for a worker quarantined for
a restore mismatch, once, and gives it work only from the generation after the fault. A second fault quarantines the
alias. A device credential may act for its own alias. The lab supervisor no longer puts a device aside after one fault
that ended in a successful rejoin; a second fault, a failed recovery or a quarantined exit still do. Device approval and
contribution are never changed. Enabled for Recipe v3 product workers (`run_worker.py`), the product runner and the
standalone `heteroes.v3 serve/worker`.

Checks: `tests/ledger/test_restore_recovery.py` (7), supervisor reconciliation (4 cases), in-place reload test;
mutation [checks/mutation-01.log](checks/mutation-01.log) **10 of 10 killed** (first run's survivor kept);
`tests/ledger`, `tests/v3`, `test_e2e_local.py`: 1589 passed, 7 skipped.

## What this does NOT show

No real GPU restore fault was produced (faults are injected); the lab UI does not yet show the recovered alias.
