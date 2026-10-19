# Desktop native profile reference and CPU regression

This folder is new M3a evidence; prior M1/M2 experiments are preserved.

`reference.json` combines the actual M2 Linux GPU reward for generation 0,
candidate 0 of run `d09d6ea8ac904cc7be92fa833637abde`, seed 3143846162412201,
with a full canonical CPU perturbation/restore hash computed on the pinned Qwen
checkpoint. Parent SHA and recipe were checked against that run's ledger. This
CPU operation did not run model inference or use a GPU. It is not a new native
Windows measurement and does not claim equality for every model/workload/seed.

The desktop gate executes the same fixed candidate twice using the existing
CandidateExecutor, FP32 evaluation, canonical CPU noise and chunk 16. Both
observations must agree, match recipe/parent/perturbed/restore/reward reference,
and restore exactly to the parent. Actual native Windows GPU qualification and
a short Windows-worker/Linux-coordinator run remain the owner's next hardware
trial. Do not mark Windows accepted from the Wine bootstrap test.

`pytest-cpu.txt`: 2041 passed, 100 skipped with CUDA hidden; skipped tests require
CUDA or opt-in conditions. `mutation.txt`: a scratch-only mutation ignoring
process birth in the stop marker was caught by its regression test. Production
files were unchanged by the mutation.

Product installer, browser, fresh isolated Linux setup and Wine bootstrap evidence
are in Track B `docs/evidence/2026-10-10-m3/`. These sources were packaged into the
checksum-pinned Worker resources without credentials, environments or model weights.

A seed-0 prediction probe also compares all 16 answer texts and reward with
the preserved 2026-10-07 FP32 Linux GPU sweep, whose file SHA is recorded.
The original reference before this addition is preserved in reference-initial.json.
