# P-FROZEN review fixes — 2026-10-31

Before frozen source is byte-identical to `58cf278c` / `f07a509a` (A1/A2 did not touch noise/es/ledger).
`frozen-source.patch` records every changed line and its context. The scratch probe is deliberately not committed,
per the approved plan. Probe SHA-256: `17d13ad47b66a27aa17f47fd70578fb921ad876f20cfbd5a50ec271fc1c220f8`.

## Changes and reasons

| File | Reason |
| --- | --- |
| es/checks.py, es/update.py, es/cuda_ops.py | A-001 rejects alpha overflowing float32 before writes; nonfinite updated FP16 weights raise explicitly. A-003 shares coefficient/seed/length/no-op checks and keeps public UpdateReport imports available from update.py. |
| es/cuda_ops.py | A-002 spells the float32 reciprocal explicitly. The prerequisite compared 8,192 random FP32 values for every n=1..4096 on both 5070 Ti and 3060: no differing bits. |
| es/perturb.py, es/cuda_ops.py, noise/contracts.py | A-007 rejects invalid seed/chunk integer identities, even for an empty schema; engine seed range remains unbounded. |
| noise/engine_v2_cuda.py | A-008 logs a self-test failure once per device, caches it under a lock, and exposes fallback diagnostics without changing noise. |
| ledger/ledger.py | A-013 BEGIN IMMEDIATE makes membership insertion idempotent across connections. A-014 durably exempts old quarantined attempts on release. A-016 adds experiment/generation-scoped read-only audit counts. |

## Numerical and ledger evidence

- Before and after JSON files are **byte-identical** on each device: CPU 576 fingerprints; 5070 Ti 694 fingerprints.
- Cases cover v1/v2 noise, multiple seeds/tensors/chunks; perturb; coefficient and reward updates with candidate counts
  1,2,3,7,32,33,512, three alpha values and coefficient styles; tied toy weights and an actual slice of pinned Qwen.
  GPU includes the legacy CUDA engine and v2 GPU-vs-CPU noise checks. Reports and a deterministic ordinary ledger
  lifecycle are also included in the byte-identical JSON.
- A-014 is an explicitly requested state correction, not numerical parity: an old-source DB reproduces OPEN/charged=1
  -> release -> FAILED/charged=2. The same old DB, opened/migrated by new code, remains OPEN/charged=1 after release;
  a future ordinary attempt counts and fails at charged=2. Logs contain only state/counts, never lease tokens.
- CPU regression: 1,977 passed / 113 skipped (GPU/optional real-model cases not enabled).
- GPU regression before removing impossible CPU/CUDA parameter combinations: 612 passed / 8 skipped; the remaining
  real-Qwen cases and all zero-skip noise/ES acceptance checks are registered for A6 on local/WSL/native.
- Final ledger/recovery/metadata regressions: 52 passed. New review mutation controls: 65 passed; 16/16 mutants killed.
  Five skips in that receipt were impossible CPU-model/CUDA-engine combinations; the final tests separate those
  combinations so GPU acceptance can require zero skips. No numerical implementation changed in that test-only cleanup.
- Qwen full model, 494,032,768 parameters, v2 update with 32 candidates, nine interleaved timing pairs:
  median before 2.162756 s; after 2.178083 s; +0.7087%, below the approved 1% cap. Keep finite checks.
- check-noise-v2.py: passed independent boundary oracle, golden v1/v2 fingerprints and non-power-of-two update.

Commands use `~/miniforge3/envs/heteroes-match/bin/python`, PYTHONPATH=runtime/src:runtime/tests/ledger, and
HETEROES_GPU_ACCEPTANCE=1 for GPU / CUDA_VISIBLE_DEVICES='' for CPU. Scratch probe invocation:

```bash
python .scratch/review-2026-11/frozen_probe.py --device cpu --model .scratch/strict-integer-20261025/models/qwen/model.safetensors --out .scratch/review-2026-11/frozen-after-cpu.json
python .scratch/review-2026-11/frozen_probe.py --device cuda --model .scratch/strict-integer-20261025/models/qwen/model.safetensors --out .scratch/review-2026-11/frozen-after-cuda.json
python .scratch/review-2026-11/bench_update.py
python scripts/check-noise-v2.py --out .scratch/review-2026-11/noise-v2.json
```

## What this does NOT show

These are bounded deterministic probes and local targeted suites, not an exhaustive enumeration of all valid inputs.
They do not yet establish final-source full acceptance or noise/ES on 3060 WSL/native; A6 will provide those receipts.
A-014 deliberately changes the faulty release transition; it is not claimed byte-identical. Runtime safety checks are
not transactional model rollback: on an invalid overflow the model must be reconstructed from checkpoint. No live lab
DB or state was used. The owner's later explicit permission allowed unrestricted machine/GPU use; only status was run
against the deployed lab. Throughput and other architectures are not established by this update-only benchmark.
