# Frozen int8 CPU oracle — 2026-10-25

Scope: first M6 feasibility step on `work/deepseek-v4-1-flash-2026-10-25`, implementation commit
`e0b1d57c2c74d3dd176997af1b89d40aa1613fb5`. This adds the versioned frozen-int8 base artifact, its exact
host-side quantizer/reader, and an exact CPU B22 projection oracle. It does not select a backend or complete M6.

## Added

- `runtime/src/heteroes/eval/frozen_int8.py`: signed per-output-row int8 weights in `[-127, 127]`, one FP32
  scale per output row rounded up to the least representable value not below `absmax/127`, canonical
  `HESFINT8` container with strict header/tensor/file hashes, and an exact CPU projection using existing B22
  activation rows. The reference projection has no full dequantized weight tensor and uses one final
  RNE/FTZ encoding per output element.
- `runtime/tests/eval/test_frozen_int8.py`: independent Fraction/bit-search oracle for the ceiling and RNE
  rules, scale/subnormal/overflow boundaries, header tamper and noncanonical JSON rejection, artifact
  determinism, and projection equality under row permutation, output tiles, bias and 1D input.
- `runtime/docs/frozen-int8-artifact-v1.md`: format contract, projection equation, exactness argument, failure
  modes and explicit limits.

Identity: format `heteroes.frozen-int8-b22`, version 1, operator
`frozen_int8_b22_exact_reference_v1_experimental`, quantizer
`per_output_channel_int8_ceil_absmax_over_127_rne_v1_experimental`. The approved plan hash remains
`4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.

## Verification

CPU only (`CUDA_VISIBLE_DEVICES=''`), Python 3.12.14, torch 2.13.0+cu132 on Linux x86-64.

| Check | Result | Receipt |
| --- | --- | --- |
| Targeted oracle/format tests | `53 passed` | `checks/frozen-int8-tests.txt` |
| Full `runtime/tests/eval` | `562 passed, 303 skipped` | `checks/eval-suite.txt` |
| Mutation check | control passed; 16 of 16 mutants killed | `checks/frozen-int8-mutation.txt` |
| Ruff format/check | formatted; all checks passed | `checks/ruff-format.txt`, `checks/ruff-check.txt` |
| Source/plan identity | commit and SHA-256 values recorded | `checks/source-identity.txt` |

Mutation coverage includes the ceiling direction, ties-to-even in weight quantization and final encoding,
minimum row scale, `-128`, zero-scale/zero-row relation, negative and nonfinite scales, canonical/duplicate
header handling, descriptor dtype, integer header identity, exact FP32 maximum, subnormal FTZ, projection
exponent, normal-scale hidden bit, encoder exponent floor, and both expected file and tensor hashes.

## What this does NOT show

- No CUDA operator, graph integration, typed base storage or trainable-adapter module exists yet.
- No real model was quantized; no pinned model artifact, model-quality result, training run, throughput,
  lifecycle peak or cross-GPU token/logit equality exists for this identity.
- The CPU oracle is intentionally slow and is not a performance candidate.
- The binary64 division argument and the exact encoding bound are documented proofs and tests, not a
  machine-checked formal proof.
- The writer validates structural invariants only. It does not re-quantize or prove that supplied `q`/`scale`
  came from the claimed source weights; provenance must be pinned by metadata and the file hash.
- No `scripts/check-all.sh`, packaging check, managed-recipe change, deployment or device-state change was
  performed. Existing experimental identities and `hardwareQualified: false` remain unchanged.

## Reproduce

```bash
cd /home/pc5070ti/projects/heteroes-deepseek-flash
CUDA_VISIBLE_DEVICES='' PYTHONPATH=runtime/src \
  /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest runtime/tests/eval/test_frozen_int8.py -q
CUDA_VISIBLE_DEVICES='' PYTHONPATH=runtime/src \
  /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest runtime/tests/eval -q
/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python scripts/mutation-check.py \
  --repo runtime --copy src --copy tests/eval/test_frozen_int8.py \
  --env PYTHONPATH=src --env CUDA_VISIBLE_DEVICES= \
  --test "/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q tests/eval/test_frozen_int8.py" \
  --mutants .scratch/frozen-int8-mutants.json --scratch /tmp/opencode
```
