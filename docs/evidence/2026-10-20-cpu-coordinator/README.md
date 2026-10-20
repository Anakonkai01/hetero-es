# CPU-only coordination (2026-10-20)

The CPU coordinator uses the `coordinator-cpu-v3` profile. Admission checks canonical noise and two repeats of a fixed
three-seed update, rather than comparing generated texts with a GPU reference. The backend validates the pinned evidence,
allows v3 coordination without per-model text qualification, excludes the profile from workers/probes, reserves its device
until confirmed drain and never reserves a nonexistent GPU. The agent passes its configured CPU device to the runner.
The device configuration route also removes its stale Linux/11 GB coordinator gate.

## Receipts

- `runtime-before.log`, `backend-before.log`: tests written before implementation; missing module and missing behavior.
- `update_oracle.py`, `update-oracle.json`: independent NumPy update formula, using production canonical noise/schema.
  The fixed vector exposes nine FP16 element differences if multiplication by the FP32 reciprocal is reverted to true
  division. Baseline initialization uses exact binary fractions and no platform-dependent Torch RNG.
- `runtime-first.log`: 7 new tests pass; `runtime-regressions.log`: 62 targeted runtime tests pass.
- `backend-first.log`: initial fixture assertion used a public assignment view lacking private fields; corrected by
  reading the assignment through the existing test helper. `backend-regressions.log`: 65 backend tests pass.
- `http-runner.log`: 11 managed v3 tests pass with real loopback HTTP and subprocess workers, now exercising the actual
  `python -m heteroes.product.runner ... --device cpu` entry point (full/subset/LoRA and Python scoring included).
- `mutation-runtime.log`: 5/5 mutants killed, including incorrect update acceptance, missing update, CPU/CUDA launch
  mismatch, CPU worker launch and true division. The frozen file is mutated only in disposable scratch copies.
- `mutation-backend.log`: 7/7 mutants killed, including forged evidence, CPU worker selection, coordinator qualification,
  GPU identity requirements, legacy reservation handling and the stale big-GPU configuration gate.

## What this does NOT show

- No new GPU execution, real multi-machine run or Windows coordinator acceptance is established by these CPU receipts.
- The tiny offline model HTTP tests establish mechanics, not numerical compatibility for an arbitrary real model.
- CPU validation texts can differ from GPU texts; model qualification still applies to each GPU worker.
- The synthetic known-answer check provides no full-model speed estimate. No live lab deployment or installer publication.
