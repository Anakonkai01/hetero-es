# Delivery heartbeat, restart outbox and local restore poison

Continuation of M2 on top of `8dcfb6a`; this is not completion of the approved plan.

## Behavior

- Heartbeat stays active through computation, restore, submission and pending transport retries. Terminal ACK,
  stale/refusal, or closing the worker stops its heartbeat. Closing does not erase pending durable state.
- Results and typed failure reports are written before transmission and drained before another lease, job fetch or
  parent synchronization. A lost response after canonical commit replays the exact request and receives
  ALREADY_COMMITTED. Text digest, usage and chunk survive restart independently of new client defaults.
- A restore mismatch poisons the worker before persistence/network reporting. The poison survives both a missing
  report ACK and restart; acknowledging or rejecting the failure cannot make the worker accept new work.
- `worker_outbox.py` keeps one record, capped at 1 MiB including its envelope. Atomic replacement, private 0600
  files, checksum validation, worker/endpoint/recipe scope and assignment/payload checks protect delivery state.
  A failed/oversized write preserves the earlier record and blocks delivery/new work. File and containing directory
  are fsynced on Linux; Windows has only the file flush here and has not been accepted.
- The managed agent passes a private assignment directory through `run_worker.py --delivery-state-dir`; it is
  shared across worker launch numbers and separate from the configured large weights cache. `WorkerRuntime` also
  accepts an explicit directory. Its generic default is beside the cache; non-managed callers selecting an external
  cache must explicitly select private delivery storage. A cancellation-only handle still needs no model/recipe.

Canonical ledger, noise, update ordering and historical identities are unchanged. No deployed worker/lab was touched.

## Checks and retained failures

- `delivery-red-01.log`: initial heartbeat/durability/poison reproductions.
- `delivery-green-01.log`: 123 worker/client/heartbeat tests passed.
- `delivery-regression-01.log`, `-02.log`: 156 then 160 worker/runtime tests passed.
- `delivery-restart-heartbeat-red-01.log`: restart initially lost the heartbeat interval; the persisted interval fixes it.
- `delivery-private-state-red-01.log`, `delivery-private-state-green-01.log`: new path/relaunch checks; the first
  green attempt also reused a fixture command ID and was correctly deduplicated before launching. The fixture now
  sends a distinct relaunch command. `delivery-private-state-green-02.log`: **88 passed**.
- `delivery-mutation-01.log`: 13/13 killed. The final `delivery-mutation-02.log`: control **16 passed**,
  **16/16 killed**, adding private storage across relaunches and cancellation without touching a model.
- `checks-01/`: complete CPU repository matrix. The first runtime run caught the cancellation constructor regression:
  1 failed, 2,834 passed, 186 skipped. Every other step passed, including backend, source packages, format/lint,
  types/i18n, web builds, browser fixtures and Electron fixtures. Preserve this initial failure as recorded.
- After correction, `runtime-tests-02.log`: **2,837 passed, 186 skipped**. Current lint/format receipts are
  `python-{lint,format}-02.log`. `packaging-01.log` validates fresh Linux unpacked Worker/Server source-copy packages.
  `checks-overview-02.json` combines these without relabeling the initial check-all invocation as ALL PASS.

Reproduce the final mutation matrix with `scripts/mutation-check.py`, `delivery-mutants-02.json`, copies of
`runtime/src` and `runtime/tests/ledger`, CUDA disabled, and tests:

```text
tests/ledger/test_worker_delivery.py
tests/ledger/test_device_agent.py::test_delivery_state_stays_private_and_is_shared_by_worker_relaunches
tests/ledger/test_product_control.py::test_worker_recognizes_cancelled_without_touching_model
```

## What this does NOT show

Tests recreate Worker/WorkerRuntime against real JSON messages and private files; they do not demonstrate a real
power failure, native Windows durability or a deployed multi-GPU run. The checksum detects accidental corruption,
not a hostile owner of the private state directory. Transport authentication remains authoritative.

The endpoint/recipe scope refuses foreign outstanding state. Changing coordinator routes or recovery identity needs
explicit reconciliation with the recovery state machine. This change deliberately does not clear poison or implement
D10 reload/self-test/probation/boundary rejoin and its persisted once-per-worker/run allowance.

Bounded usage delivery, audit controls/statuses, progress watchdogs and hard caps, large text payload transport,
M3 recovery I/O, strict throughput/batching, M4 managed numerical lifecycle/SDK/packaging, M5 and M6 remain open.
No acceptance/default/deployment decision follows from these CPU tests or basic application packages.
