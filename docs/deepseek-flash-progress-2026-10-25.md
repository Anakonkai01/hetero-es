# DeepSeek Flash trial progress — 2026-10-25

Branch: `work/deepseek-v4-1-flash-2026-10-25` in `/home/pc5070ti/projects/heteroes-deepseek-flash`.
This is the isolated DeepSeek trial branch; it is not merged, pushed or audited by Codex yet. The Codex worktree
`/home/pc5070ti/projects/heteroes` was not modified.

The approved M0–M6 objective and the plan hash are unchanged:
`4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`. No learning run, deployment, device-state
change, shared-environment change or model-asset copy was performed. CPU checks use `CUDA_VISIBLE_DEVICES=''`; the
GPU checks below ran only with `HETEROES_GPU_ACCEPTANCE=1` and explicit opt-in.

## Commits on this branch

| Commit | Purpose |
| --- | --- |
| `253ebb98` | Implementation baseline named by the handoff. |
| `da009182` | Add the isolated DeepSeek trial handoff. |
| `79681d88` | Audit pinned vLLM/SGLang/TensorRT-LLM source for M6 placement and constraints. |
| `e0b1d57c` | Add the exact frozen-int8 base artifact, CPU quantizer/reader and B22 projection oracle. |
| `3ed26c68` | Record the frozen-int8 oracle tests, mutation check and source identity. |
| `39aefba9` | Content-address canonical artifact bytes and define the adapter combine contract. |
| `f4ef2884` | Add typed int8 base storage with FP16 LoRA-only adapters and pinning. |
| `b8648792` | Add the exact three-limb frozen-int8 CUDA projection. |
| `fe7c472b` | Integrate frozen projections into strict captured decode and update the format doc. |

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

### M6 step 2: typed storage, CUDA operator and graph integration

Artifact bytes are now content-addressed by `artifact_bytes`/`artifact_digest`, so a typed module can carry the
exact writer digest without a file. `FrozenInt8LoraLinear` keeps `weight_q`, `weight_scale` and an optional FP16
bias as buffers, has no dequantized `.weight`, and leaves only FP16 `lora_A`/`lora_B` trainable. Embeddings and a
possibly tied LM head stay FP16. Adapters are deterministic from a caller seed and adapter files use the existing
weights format.

`frozen_int8_cuda.py` is a separate `frozen_int8_b22_mma_cuda_v1_experimental` identity. Each dot uses three signed
byte MMA products (one weight limb), with SIMT decode, split-K where the plan selects it, shared activation
quantization for `linear_many`, a two-limb `S * signif(scale)` product and one exact RNE/FTZ encoding. It never forms
int64-by-FP32. A zero adapter delta preserves the exact base bits, including signed zero; a nonzero delta uses the
adapter's separate ordinary FP32 namespace and is not claimed bit-identical across devices.

`describe_graph(..., frozen_int8=True)` validates the typed storage, pinned digest, adapter set/shapes/dtypes/grad,
bias and module configuration, and rejects the mode when it selects no typed projection. `FrozenInt8DecoderReference`
and `FrozenInt8DecoderGraph` compose the CPU oracle and captured decode; the graph reports `frozenKernels` separately
and invalidates capture when a frozen buffer moves or is replaced. The existing strict FP16 kernels remain unchanged
and are still used for embeddings, normalization, attention and mixed non-frozen projections.

Verification for the four commits above:

- full CPU runtime suite: `3116 passed, 426 skipped`;
- CUDA operator plus frozen graph with explicit GPU opt-in: `31 passed` (`22` operator, `9` graph);
- mutation checks: `8 of 8` storage/artifact mutants, `3 of 3` graph mutants (one killed by the GPU recapture test)
  and `5 of 5` CUDA mutants killed;
- Ruff format/check clean on every changed file.

Receipts are in `docs/evidence/2026-10-25-frozen-int8-integration/`.

## Not yet done

- No real-model frozen artifact bundle and no SmolLM2/TinyLlama/Qwen quality, reward, token, lifecycle or throughput
  measurement under this identity.
- No measured speed improvement. The three-limb work count is a hypothesis; activation quantization, encoding and
  launch overheads are unmeasured.
- No cross-GPU bit equality with nonzero adapters, no SM86/SM120 comparison, no hardware qualification.
- No `scripts/check-all.sh`, packaging acceptance, managed-recipe change or Codex audit.
- M0–M5 items and the rest of M6 remain required as listed in the handoff.

## Next step

Build pinned real-model artifacts, then measure the frozen-base/LoRA path separately from full-weight FP16 ES on
SM86 and SM120: quality/tokens/rewards, lifecycle peak memory and throughput. Report unfavorable or unchanged speed
honestly; do not reinterpret an existing artifact under a changed quantizer, scale or encoding rule.
