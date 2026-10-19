# Recipe v3 — ledger schema 6, generation record 2, descriptor sign

Baseline: `45bf10a` (ADR-008 accepted by the owner), branch `feat/extensibility-step0`. First change to frozen modules
under ADR-008: `ledger/ledger.py`, `generation_record.py`, `manifest.py` (descriptor), plus `coordinator.py` and
`replay.py` (records are applied through `update_inputs()`). `noise/` and `es/` are unchanged.

## What changed

- **Descriptor**: `sign` (+1 or −1, an `int`), not part of `candidate_id`; a stored descriptor without it means +1.
- **Ledger schema 6**: `candidate.sign`, `UNIQUE (experiment, generation, seed, sign)`; `completion` (the texts behind a
  committed reward: SHA-256 of the canonical JSON list, zlib body, written in the transaction that commits the reward);
  `audit` and `record_audit` (a mismatch counts against the auditor and the original worker; at
  `AUDIT_QUARANTINE_AFTER = 3` mismatches a worker is quarantined with reason `AUDIT_MISMATCH`; committed rewards never
  change); `quarantine.reason`. A schema-5 file (Recipe v1/v2) is refused as history and left byte-identical: it is
  replayed, never continued (ADR-008 section 9; nothing migrates old ledgers).
- **Record version 2**: `signs` and `coefficient_rule` (`zscore@1`); pairs are validated with the antithetic merge rule;
  `update_inputs()` gives what `apply_coefficients_` receives. Without them a record is version 1, byte for byte: the 418
  recorded records still hash and serialize exactly as recorded (`test_golden_identities.py`).

## Receipts

| Check | Result | File |
| --- | --- | --- |
| Full CPU product check | 22/22 PASS; runtime 2,203 passed, 100 skipped; backend 287 passed | `check-all.log`, `checks/` |
| Mutation check | control passes; 15/15 killed | `mutants.json`, `mutation.log` |

Not covered by a mutant: the `signs` comparison inside `record_update`. Every valid record already says the committed signs
(a version-1 record cannot even be built for a pair), so that comparison is a second line of defence that no valid input
reaches. The coordinator's use of `update_inputs()` is exercised only with version-1 records here: the antithetic
coordinator path is the next step.

## What this does NOT show

No worker or coordinator produces version-2 records or texts yet (the worker protocol is unchanged), no audit is scheduled,
no GPU, no product run. The product's raw ledger readers (`run_supervisor.py`) read columns by name and were not changed.
