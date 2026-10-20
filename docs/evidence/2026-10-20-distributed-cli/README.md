# Standalone coordinator and workers (2026-10-20)

`heteroes serve` runs the existing Coordinator against external processes; `heteroes worker` fetches and validates pinned
recipe/plan/data, loads only its own verified model files, then uses the existing candidate executor and WorkerRuntime.
`/v1/inputs` is opt-in and uses the existing bearer authentication. Python source is never in the bootstrap documents.
Native Windows LoRA coordination requires an existing pinned adapter file.

## Receipts

- `before.log`: five initial failures before implementation.
- `first.log`: three test assertion failures: the existing HTTP client returns a structured 404 body, and WorkerRuntime's
  terminal event is named `exit`; tests were corrected to those existing contracts. Both distributed cells had already
  reached the same numerical children as their baselines.
- `second.log`: 5 passing tests, including independent coordinator + two worker processes for full weights and LoRA,
  matching every child to one-machine runs with Python scoring. A scorer import raises if attempted in a worker.
- `regressions.log`: 108 passed, 1 skipped (existing HTTP and hardening regressions included).
- `mutation-complete.log`: 7/7 mutants killed, including missing credentials, corrupt data, identity drift,
  Windows adapter creation and ignored seed namespaces. `mutation.log` belongs to the interrupted first mutation attempt:
  removing the missing-secret gate let its negative test enter the coordinator wait; that test now passes a 0.1-second
  generation timeout. A second attempt (`mutation-final.log`) exposed the same wait in the Windows-adapter negative test;
  it too now has a short generation timeout. Both owned process trees were terminated. The complete run has an additional
  90-second per-command bound; all controls/mutants actually finish in about 16 seconds. No pass/kill is inferred from an
  interrupted run.

## What this does NOT show

- CPU fixture tests do not qualify a real model/device or show learning. Real native Windows/3060 evidence is separate
  in `../2026-10-20-windows-coordinator/` with a source-file digest inventory.
- The standalone bootstrap uses an inline local dataset document; the managed lab's file-backed upload/transfer path is
  separate. The token authenticates trusted peers over private HTTP, not a new public Internet security boundary.
- No installer, live device approval, deployment or public release follows from these tests.
