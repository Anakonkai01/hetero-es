# Optional token and GPU-time accounting checkpoint (2026-10-20)

Generated token counts include the first EOS, exclude padding after EOS and are opt-in in the old evaluation helper.
Worker/coordinator negotiation keeps old coordinators' request bodies unchanged. Usage does not enter text, recipe,
record or child-weight hashes. A separate private usage.sqlite records successful candidate/audit executions and
coordinator updates. Retries are idempotent; changed receipts are refused. A sidecar write failure cannot invalidate a
canonical successful submission. CPU work costs zero GPU seconds. Missing receipts are explicitly partial.

Runtime, backend snapshots and web experiment/generation/candidate pages expose these receipts. Recovery includes a
SQLite backup. Tests also found and fixed an existing recovery allowlist/maximum-count bug for file-backed datasets:
v2 permits the three hashed JSONL splits plus usage.sqlite (maximum 12 files including LoRA and selection); v1 is unchanged.
Checkpoint evaluation now opens/verifies file-backed datasets and checks their identity against recipe.data. Evaluation
still materializes the selected split for output/reporting; this is not a streaming evaluation-memory claim.

- `regressions.log`: 81 runtime/product/audit/worker/recovery tests pass (correct runtime working directory).
- `projection-final.log`: 8 projection/accounting tests pass. The preceding failure exposed the old worker-*.json glob
  also reading worker-config.json as event rows; the glob is now worker-*-r*.json and row shapes are checked.
- `combined-final.log`: 21 option/accounting/evaluation tests pass, including real managed file-backed evaluation.
- `checkpoint-final.log`: later focused suite after formatting; consult its terminal result for the exact count.
- `mutation-final.log`: 9/9 mutants killed, including retry accounting, EOS, compatibility negotiation and recovery.
  The first scratch control could not locate the recovery CLI in a flattened copy; no mutations were attempted then.
  Final mutation selection excludes the subprocess recovery tests; they pass separately in the proper repository layout.
- Red/failed intermediate receipts are retained. `with-recovery.log` used the wrong cwd for two existing subprocess
  tests; `eval-file-before.log` used a one-generation fixture whose helper expects two, `before2` had not staged split
  files beside the dataset. `before3` is the genuine unsupported-format failure. `checkpoint-final.log` supersedes these.
- Backend and frontend TypeScript checks passed in the accompanying receipts. Frozen numerical files are unchanged.

## What this does NOT show

GPU-seconds are reported synchronized execution wall time plus coordinator GPU update time, not utilization/energy or
whole-machine billing. Idle time, validation and unreported failed work are excluded. Worker reports are not independently
attested. No full check-all after this code, packaged candidate3 acceptance or deployed usage telemetry is claimed.
The new evaluation file-data regression and download changes still need their own mutation coverage.
