# DeepSeek Flash trial progress — 2026-10-25

Branch: `work/deepseek-v4-1-flash-2026-10-25` in `/home/pc5070ti/projects/heteroes-deepseek-flash`.
This is the isolated DeepSeek trial branch; it is not merged, pushed or audited by Codex yet. The Codex worktree
`/home/pc5070ti/projects/heteroes` was not modified.

The approved M0–M6 objective and the plan hash are unchanged:
`4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`. No learning run, deployment, device-state
change, shared-environment change or model-asset copy was performed. All checks below are CPU-only.

## Commits on this branch

| Commit | Purpose |
| --- | --- |
| `253ebb98` | Implementation baseline named by the handoff. |
| `da009182` | Add the isolated DeepSeek trial handoff. |
| `79681d88` | Audit pinned vLLM/SGLang/TensorRT-LLM source for M6 placement and constraints. |
| `e0b1d57c` | Add the exact frozen-int8 base artifact, CPU quantizer/reader and B22 projection oracle. |
| `3ed26c68` | Record the frozen-int8 oracle tests, mutation check and source identity. |

## Completed in this trial

### M6 source audit

`docs/strict-engines-source-audit-2026-10-25.md` records the audit of pinned vLLM
`e7473bf6862289f0647d1f4b01498288b181e063`, the SGLang 0.5.22 wheel and TensorRT-LLM
`376f7e1bd8ed543f75014309e3fd4b237e9b0e73` (`v1.2.1`). The adopted pattern is a quantized frozen base GEMM
whose adapter reads the original activation and adds its delta at the output. Their quantization arithmetic and
vendor kernels are not adopted. Exact source pins are in
`docs/evidence/2026-10-25-engine-source-audit/SOURCE-INDEX.md`.

### M6 step 1: frozen-int8 artifact and CPU oracle

`runtime/src/heteroes/eval/frozen_int8.py` implements:

- signed per-output-row int8 weights restricted to `[-127, 127]`, with one FP32 scale per output row;
- scale `ceil_fp32(absmax/127)`, the least FP32 value not below the exact rational maximum, so no clipping is
  needed and `-128` is never emitted;
- exact ties-to-even weight rounding, with a documented distance/error argument for the binary64 quotient;
- the canonical little-endian `HESFINT8` container with strict header keys/types, canonical JSON, exact file
  size, tensor SHA-256 values and optional whole-file pinning;
- a CPU B22 projection: exact int64 dot, exact Python-integer `S * signif(scale)`, one final RNE/FTZ encoding,
  then the existing reference FP16-bias add;
- no full dequantized weight shadow, and an identity API that still reports `hardwareQualified: false`.

`runtime/docs/frozen-int8-artifact-v1.md` is the format contract, including the `|T| < 2^68` projection bound,
the 96-bit product requirement for future CUDA work, and the provenance limit of the writer.

Verification for `e0b1d57c`:

- `runtime/tests/eval/test_frozen_int8.py`: `53 passed`, using an independent Fraction/bit-search oracle;
- full `runtime/tests/eval`: `562 passed, 303 skipped`;
- mutation check: control passed, `16 of 16` mutants killed;
- Ruff format/check passed for the new module and test.

Receipts are in `docs/evidence/2026-10-25-frozen-int8-oracle/`.

## Not yet done

- No versioned CUDA two-limb operator; the CPU encoder is the oracle only.
- No typed frozen-base storage, LoRA-only trainable module or tied-storage integration.
- No graph integration, real model artifact, model-quality result, training run, throughput, lifecycle peak or
  cross-GPU token/logit equality under this identity.
- No `scripts/check-all.sh`, packaging acceptance, managed-recipe change or hardware qualification.
- M0–M5 items and the rest of M6 remain required as listed in the handoff.

## Next step

Implement the separately named CUDA operator and typed storage/LoRA path against this artifact identity, then
run smoke/boundary tests before graph integration. Do not reinterpret an existing artifact under a changed
quantizer, scale rule or encoding rule; create a new versioned identity instead.
