# DeepSeek Flash trial progress — 2026-10-25

Branch: `work/deepseek-v4-1-flash-2026-10-25` in `/home/pc5070ti/projects/heteroes-deepseek-flash`.
This is the isolated DeepSeek trial branch; it is not merged, pushed or audited by Codex yet. The Codex worktree
`/home/pc5070ti/projects/heteroes` was not modified.

The approved M0–M6 objective and the plan hash are unchanged:
`4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`. No learning run, deployment, device-state
change, shared-environment change or model-asset copy was performed. CPU checks use `CUDA_VISIBLE_DEVICES=''`; the
GPU checks below ran only with `HETEROES_GPU_ACCEPTANCE=1` and explicit opt-in.

## Commits on this branch

| Commit     | Purpose                                                                                  |
| ---------- | ---------------------------------------------------------------------------------------- |
| `253ebb98` | Implementation baseline named by the handoff.                                            |
| `da009182` | Add the isolated DeepSeek trial handoff.                                                 |
| `79681d88` | Audit pinned vLLM/SGLang/TensorRT-LLM source for M6 placement and constraints.           |
| `e0b1d57c` | Add the exact frozen-int8 base artifact, CPU quantizer/reader and B22 projection oracle. |
| `3ed26c68` | Record the frozen-int8 oracle tests, mutation check and source identity.                 |
| `39aefba9` | Content-address canonical artifact bytes and define the adapter combine contract.        |
| `f4ef2884` | Add typed int8 base storage with FP16 LoRA-only adapters and pinning.                    |
| `b8648792` | Add the exact three-limb frozen-int8 CUDA projection.                                    |
| `fe7c472b` | Integrate frozen projections into strict captured decode and update the format doc.      |
| `e03307ae` | Add explicit vendor-FP16 fast-path decoder experimental baseline.                        |
| `cc76a03d` | Harden frozen-int8 rounding, artifact seal, strict adapter arithmetic and limb sign.     |
| `f9bfd254` | Fuse the strict LoRA finish and tile the first adapter product.                          |

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

### M6 audit fixes and first measured performance gain

Audit A–D from the continuation handoff were addressed before new speed claims:

- A: the FP32 RNE overflow midpoint is fixed in the CPU oracle/encoder and the CUDA encoder; below/at/above the
  midpoint, both signs, min-normal and signed FTZ are covered, including the `linear` case `0x7F7FFFFF`.
- B: `FrozenInt8Artifact` now recomputes its digest at construction and carries a version+metadata seal; the reader,
  typed module and decoder re-verify ownership/admission at construction and the request boundary, not per token.
- C: the adapter delta uses the strict pairwise FP32 contract (`ops.linear` twice, strict scalar multiply, strict add
  with zero-delta preserving the base bits) on CPU and CUDA. Non-finite inputs and canonical ± ES perturbations are
  covered; zero-initialised B is no longer the only evidence.
- D: signed limbs use defined `combine_limbs` multiplication instead of signed left shifts; tied-head sidecar
  metadata declares storage tie only, with numerical weight
  `int8_approximation_of_storage_tied_fp16_embedding`; the FP16 decoder is explicitly labelled experimental.

Performance source `f9bfd254` makes two changes: the first rank product uses `row_tile=1`, and a new
`strict_lora_finish` kernel fuses the second rank product, strict scale, zero-delta select and strict add. The fused
kernel is tested bit-for-bit against the old sequence over ranks 1/2/3/8/16/32, odd shapes, signed zero, subnormals,
non-finite inputs, row tiles 1/2/4/8 and CUDA-graph replay. Three of three mutants (drop scale, drop add, drop
zero-delta select) were killed.

Local 5070 Ti, fixed eight-prompt decode, greedy 32 tokens, context 512, one warmup and five timed observations.
Median tokens/s (observed spread in parentheses); details and raw durations are in
`docs/evidence/2026-10-25-frozen-audit-perf/`:

| Case                        |           B1 |            B8 |           B32 |
| --------------------------- | -----------: | ------------: | ------------: |
| SmolLM2 frozen head         | 152.5 (0.9%) | 1101.4 (1.0%) | 3077.7 (0.2%) |
| SmolLM2 frozen no head      | 149.1 (0.7%) | 1021.0 (1.1%) | 2446.1 (0.4%) |
| SmolLM2 FP16 baseline       | 365.2 (1.2%) | 2229.4 (1.5%) | 7195.2 (0.8%) |
| Qwen2.5-0.5B frozen head    | 181.2 (0.8%) | 1215.8 (0.5%) | 2907.5 (0.4%) |
| Qwen2.5-0.5B frozen no head | 166.2 (1.0%) |  900.0 (0.7%) | 1521.4 (0.2%) |
| Qwen2.5-0.5B FP16 baseline  | 382.7 (1.3%) | 2477.7 (1.2%) | 7849.2 (0.5%) |
| TinyLlama frozen no head    | 149.3 (0.6%) |  785.9 (0.3%) | 1437.3 (0.1%) |
| TinyLlama B22               | 187.2 (0.4%) |  786.4 (0.2%) | 1810.5 (0.3%) |
| TinyLlama FP16 baseline     | 270.9 (1.0%) | 1655.3 (0.8%) | 4858.5 (0.6%) |

Frozen head B32 improved from 2511.8 to 3077.7 tok/s on SmolLM2 (+22.5%) and from 2413.2 to 2907.5 on Qwen
(+20.5%); B8 improved +24.0% and +24.8%. B1 is unchanged inside run noise. The intermediate row-tile-only Smol
B32 case was 2870.7. A nonzero-B probe (fixed normal fill of every `lora_B`, not a trained/ES adapter) reproduced
the same throughput within 0.2%, so the add path is not a hidden zero-delta shortcut.

The gap to the prior vLLM controls is still large: best B32 is 21.3% of vLLM on SmolLM2, 21.1% on Qwen and 18.4%
on TinyLlama. These are unmatched prior controls, not a fresh same-host comparison. The FP16 baseline reaches
49.9%/56.9%/62.4% of the same controls, so the strict/frozen gap is not only the adapter epilogue. A profile of
Smol B32 frozen head puts 71.5% of CUDA event time in projection (`frozen_linear` 32.4%, `strict_lora_finish`
26.1%, `strict_linear` 13.1%), with `strict_attention` at 12.7%.

Checks: full CPU runtime suite `3131 passed, 444 skipped`; GPU `180 passed` (`test_strict_cuda.py` plus
`test_frozen_int8_decoder_cuda.py`); Ruff format/check clean. Receipts, model file manifests, prompt IDs, the
profiler table and the "What this does NOT show" section are in
`docs/evidence/2026-10-25-frozen-audit-perf/`.

### State of this work

- **Proposed:** a matched 3060/vLLM matrix, a trained-adapter quality/lifecycle run, and the next base-projection
  kernel change.
- **Implemented:** the audit fixes and the two adapter-epilogue optimizations on this branch.
- **Tested:** the CPU/GPU suites above, bit-equality tests, the zero-B/`-0.0` select case and three mutants.
- **Selected in this trial:** the fused finish is used by the experimental `FrozenInt8DecoderGraph`; the FP16
  decoder remains a labelled non-strict baseline. No managed recipe/default has been changed.
- **Unaccepted:** every throughput number here is local, unmatched and awaiting Codex audit. `hardwareQualified`
  remains false and no managed/default path is activated.

## Not yet done

- No pinned on-disk frozen artifact bundle and no trained-adapter SmolLM2/TinyLlama/Qwen quality, reward or token
  evaluation. The benchmark adapters are random and the nonzero-B probe is not an ES perturbation.
- No 3060 matrix, no matched same-host vLLM control and no cross-GPU bit equality with nonzero adapters; the
  5070 Ti gain does not establish a 3060 gain.
- No lifecycle measurement (candidate entry, perturb, restore, reload) and no process-RSS/peak-memory acceptance.
- No `scripts/check-all.sh`, packaging acceptance, managed-recipe change or Codex audit.
- M0–M5 items and the rest of M6 remain required as listed in the handoff.

## Next step

The owner ended the current implementation session. **Codex will audit and continue next session** from the
DeepSeek checkpoint `777a0211`, performance code `f9bfd254`, and the immutable receipts in
`docs/evidence/2026-10-25-frozen-audit-perf/`. Read
`docs/handoff-codex-performance-after-deepseek-2026-10-25.md`; the older DeepSeek continuation task is superseded.

Next: audit the actual source and existing regression fixes; pin frozen-base/adapter artifacts and full-output
evidence; establish nonzero canonical-candidate/restore equality on 5070 Ti and 3060; run matched M6/B22/vLLM
controls; then implement the next projection optimization from profiles of the exact workload. The 71.5%
profile share includes base and adapter work. Trained-adapter quality remains missing unless a compatible
existing artifact is available; no learning run is authorized to create one.

Keep all old receipts immutable and the full M0–M6 scope open. This closing handoff changes documentation only;
no further kernel, GPU, deployment or integration work is started in this session.

## Codex follow-up: original shadow-FP32 comparison

The owner resumed discussion and explicitly requested this benchmark. Codex created the isolated branch
`work/codex-frozen-perf-2026-10-25` from `cb9aa2aa`, leaving the DeepSeek/original Codex worktrees unchanged.
Harness/test commit `d9a11627` adds the original `EvalModel` FP32 shadow control, timed refresh, chunked HF
control and frozen decoder selection. Numerical source remains `f9bfd254`; the full checkpoint audit and
remaining performance handoff have not been completed by this measurement.

Local 5070 Ti, same model files/prompt token IDs, greedy 32 tokens, context 512, one warmup and five timed
observations. Original full-batch HF shadow B32 Smol/Tiny/Qwen: **2425.7 / 1465.1 / 2525.8 tok/s**;
B22: **3855.4 / 1812.4 / 3471.4**; frozen: **3077.1 / 1437.1 / 2911.0** (Smol/Qwen tied-head sidecar,
Tiny untied FP16 head). Shadow refresh is included. B22 wins all nine model/batch cases; frozen wins eight
of nine. Tiny B32 A/B/B/A confirms frozen/shadow **0.98124**, a -1.88% regression. Both new paths exceed
the separately measured original chunk-16 B32 control. Preserve this unfavorable case.

B22 parent tokens equal the original shadow in this finite corpus. Frozen parent tokens differ in eight
of nine cases, so its speed is not a quality/parity acceptance. Canonical perturb/restore and full ES
lifecycle were not timed. No learning, managed activation, remote work, push, merge or deployment occurred.
Targeted harness/precision CPU checks: **34 passed, 1 skipped**; four scratch mutants killed. All benchmark
jobs are terminal. [Full receipts, commands and limitations](evidence/2026-10-25-shadow-baseline/README.md).

## Codex continuation into 2026-10-26: full-weight core and owner-authorized fast inference

Worktree `/home/pc5070ti/projects/heteroes-codex-frozen-perf`, branch
`work/codex-frozen-perf-2026-10-25`; original/DeepSeek trees remain untouched. The owner subsequently
prioritized approaching vLLM and permitted alternative arithmetic. Historical noise/ES/ledger recipes
and the approved-plan bytes remain unchanged; vendor inference has a new experimental identity.

- `9acf8bfa`: exact B22 paired weight reads selected only on SM120. Native ABBA batch-32 gains are
  5.48%/8.37%/9.98% for Smol/Qwen/Tiny; SM86 retains scalar after a measured Tiny regression.
  [Evidence, failed prototypes and candidate/restore proof](evidence/2026-10-25-b22-core-perf/README.md).
- `3735d6db`: FP16 graph v2 binds original parameters into merged storage, fixing stale ES updates.
- `c9a37059`: canonical HF parameter views over vLLM fused storage, plus an explicit standalone ES probe.
  Parent/canonical plus/minus/restore weights match B22 on both hosts without a second GPU model. Batch-32
  inference reaches 99.5–100.7% of matched vLLM controls; publication/audit time is separate. Smol has one
  cross-GPU token-row difference in this finite corpus; Qwen/Tiny have none. This is not bit-exact vendor
  inference or managed acceptance. [Fast-engine receipts](evidence/2026-10-25-fast-engine/README.md).
- The earlier selected LoRA finish `20856dea` and pinned two-host adapter/model checks are now sealed in
  [their own evidence](evidence/2026-10-25-frozen-subwarp-perf/README.md). They are a separate search space.

No push, merge, deploy, live device-state change or learning run. Broader quality/drift, candidate/update
throughput, ownership/lifecycle, native Windows and general qualification remain open.

Final checks at `c9a37059`: full check `ALL PASS` (runtime CPU 3158 passed/459 skipped, backend 452),
17 targeted tests per GPU host, four scratch mutants killed. Isolated Linux Worker/Server packages pass;
Worker and notebook SDK match all 141 runtime sources, Server shared subset matches 23. Package/import
acceptance does not establish an installed managed vLLM runtime. Live status was read only: services stopped.
