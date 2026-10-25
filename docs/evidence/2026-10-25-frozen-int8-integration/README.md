# Frozen-int8 base integration receipts (2026-10-25)

Branch: `work/deepseek-v4-1-flash-2026-10-25`, baseline `cb97f330` with the M6.2 working tree.
Environment: Python 3.12.14, torch 2.13.0+cu132, CUDA 13.2, RTX 5070 Ti (SM120).
No push, merge, deployment, learning run or shared model/environment change was performed. The Codex worktree
`/home/pc5070ti/projects/heteroes` was not touched.

## What was added

- content addressing for the canonical artifact bytes (`artifact_bytes`, `artifact_digest`), so typed modules can
  carry the exact writer digest without a file;
- `runtime/src/heteroes/model/frozen_int8.py`: typed int8 base storage, FP16 LoRA-only parameters, deterministic
  adapters, artifact pinning and the tied-head guard;
- `runtime/src/heteroes/eval/frozen_int8_cuda.py`: separate three-limb frozen MMA/SIMT operator, split-K, shared
  activation quantization and the two-limb exact encoder;
- explicit `frozen_int8=True` graph admission plus `FrozenInt8DecoderReference` and `FrozenInt8DecoderGraph`;
- frozen buffer signatures in captured decode, so a replaced buffer forces a fresh capture.

## Commands and results

Formatting and lint:

```bash
.venv-backend/bin/ruff format <changed files>
.venv-backend/bin/ruff check <changed files>
```

Result: clean.

Full CPU runtime suite (all CUDA tests skipped):

```bash
cd runtime
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src \
  /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q
```

Result: `3116 passed, 426 skipped in 226.61s`.

Frozen operator and graph with explicit GPU opt-in:

```bash
HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src \
  /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest \
  runtime/tests/eval/test_frozen_int8_cuda.py \
  runtime/tests/eval/test_frozen_int8_decoder_cuda.py -q
```

Result: `31 passed` (`22` operator tests, `9` graph tests).

Mutation checks on scratch copies:

```bash
PYTHONPATH=runtime/src python3 scripts/mutation-check.py ...
```

- storage/artifact/decoder CPU mutants: `8 of 8` killed;
- graph mutants: `2 of 2` killed on CPU, the buffer-signature mutant killed by the GPU recapture test (`1 of 1`);
- CUDA operator mutants: `5 of 5` killed (normal tie rounding, subnormal exponent, high-limb carry, activation-limb
  shift, subnormal scale exponent).

## What this does NOT show

- No real-model artifact bundle, model-quality score, reward, LoRA training run or lifecycle/throughput result.
- No measured speed improvement. The three-limb product count is a work hypothesis; launch, activation quantization
  and encoding overheads are unmeasured.
- No cross-GPU bit equality with nonzero adapter weights. Only the exact integer base with a zero adapter is compared
  bit-for-bit between CPU and CUDA; adapter deltas use a separate ordinary FP32 namespace.
- No hardware qualification, managed recipe, deployment, `scripts/check-all.sh` acceptance or audit by Codex.
- Fixtures are tiny Qwen2-style models; results do not transfer to SmolLM2/TinyLlama/Qwen or other GPUs without the
  planned measurements.
