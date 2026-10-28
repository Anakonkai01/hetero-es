# Bounded usage delivery and partial monitoring (2026-10-25)

Continuation of M2 on top of the scorer/delivery work and `82368bf`. Metrics remain outside canonical numerical
identity. This change does not finish M2 or any later milestone.

## Behavior and bounds

`v3/usage_queue.py` accepts at most 64 pending records per run by default, including the active sink call.
Each record's serialized usage and execution key are capped at 64 KiB; Python object/thread overhead is additional.
Obvious oversized token-count lists are refused before copying/serialization. Queue overflow, closure and oversized
records are dropped with visible counters instead of growing an unbounded backlog or holding a result ACK.

WorkerAPI wraps usage sinks with this queue. The coordinator shares one queue across generation APIs, so a slow
sink cannot create another backlog for each generation. Pending identical `(candidate, attempt, worker, kind)` keys
coalesce; changed metadata under that key is refused. `UsageStore` keeps the durable database idempotency rule.
The sink runs outside both API locks and the queue condition; sink errors do not kill the consumer.

Flush/close waits are finite. The coordinator's `usage_flush_seconds` defaults to 1 second and can be configured;
invalid/nonfinite/negative values fail. Closing stops new records and bounds the wait; it does not cancel a sink
call already running. This is a best-effort queue, not a crash-durable usage outbox or an exactly-once external sink.
Coordinator update-time sidecar writes still use their existing synchronous path outside canonical commit.

Generation summaries preserve delivery counters and mark usage partial on errors, drops or remaining pending work.
Managed run/generation projections retain recorded errors/drops even when row counts look complete. A historical
pending-only snapshot does not permanently label subsequently delivered, complete metrics as lost. Existing UI
partial indicators receive that state without changing any numerical ledger table or result.

## Tests and receipts

- `usage-queue-red-01.log`: slow sink initially holds the ACK; queue helpers do not yet exist.
- `usage-queue-green-01.log`: 15 targeted queue/usage/projection tests pass.
- `usage-projection-red-01.log`: recorded delivery faults initially disappear from the managed projection.
- `usage-queue-green-02.log`: retained invocation failure: the tests were run from the repository root, while the
  managed fixture launches `scripts/run_product.py` relative to the runtime directory. No product failure is inferred.
- `usage-queue-green-03.log`: correct runtime working directory, **20 passed**.
- `usage-queue-mutation-01.log`: control **8 passed**, **11/11 killed**. Covers blocking ACKs, record/byte bounds,
  active work in capacity, duplicate keys, metadata conflicts, sink errors, consumer survival and bounded close.
- `usage-projection-mutation-01.log`: scratch setup failed before control because of an incorrect tinylm helper path.
  The final `usage-projection-mutation-02.log` has control **4 passed**, **3/3 killed**, including the distinction
  between a permanent delivery fault and an old pending snapshot.
- `runtime-tests-03.log`: before the new projection cases, **2,845 passed, 186 skipped**.
- Final `runtime-tests-04.log`: **2,848 passed, 186 skipped**; `backend-tests-02.log`: **439 passed**, one warning.
- `python-{lint,format}-03.log` and `source-packages-03.log`: current lint/format and isolated source imports pass.
  `packaging-02.log`: a fresh Linux unpacked Worker/Server source-copy build passes. Browser/Electron/type/i18n
  checks from `checks-01/` remain recorded; no frontend implementation changed in this step.
- `checks-overview-03.json` identifies the final combination and preserves the earlier check-all failure.

The final observation receipt confirms no owned SGLang probes remain on Thao or Quang; local GPU usage returned to
30 MiB/0%. The deployed clone remains `82c37fc`; its three lab services remain stopped. No push, merge, deployment,
learning run or device approval/contribution change was performed.

## What this does NOT show

No measured physical-memory/throughput acceptance for the queue, hard-power-loss guarantee for usage, arbitrary
external sink exactly-once effects, native Windows acceptance, or new numerical/backend qualification.
The remaining M2 work is audit controls/statuses, stage/progress watchdogs with explicit hard caps and the D10
recovery state machine. M3, strict backend throughput work, M4, M5 and M6 remain in the approved scope.
