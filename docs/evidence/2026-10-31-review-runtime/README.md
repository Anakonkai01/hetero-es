# Review A2: schema, restore classification and coordinator recovery

Baseline `129f43cd`, 2026-10-31. New regressions fail on a scratch archive of the baseline source:
26 failed / 5 passed. Final targeted regressions before the last extra boolean-numel case: 253 passed / 5 skipped.
Mutation control includes that extra case: 32 passed, 96 deselected; 16/16 mutants killed.

- A-004: immutable and consistent SchemaEntry layouts; existing hand-written hash oracles remain unchanged.
  Two existing tests now construct internally valid changed layouts (shape and numel agree), then test hash sensitivity
  or mismatch with the actual model; their original purpose remains intact.
- A-015: resumed populations must match stored count, canonical index, seed and sign. Namespace/antithetic changes fail.
- A-017: every Exception during restore becomes RESTORE_MISMATCH; KeyboardInterrupt still propagates.
- A-019: interrupted in-place application makes that Coordinator unusable. A new object from checkpoint recovers the
  correct oracle hash; recover also hashes actual model bytes before trusting the cached parent.

Tests: tests/model, tests/eval/test_executor.py, tests/ledger/test_coordinator{,_recovery,_v3}.py.
The mutant recipe in this folder records the exact edits. Use scripts/mutation-check.py with copies of src and these
fixture/test modules; CUDA_VISIBLE_DEVICES='' and PYTHONPATH=src. Selected regressions are the new review test names.

## What this does NOT show

This CPU receipt does not establish GPU or full acceptance. A-008/A-016 require frozen-region work in A3 and are not
included in this commit. No frozen numerical or ledger source was changed in A2. Full A6 and parts B/C remain open.
