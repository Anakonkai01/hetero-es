# Strict engines source audit: vLLM, SGLang, TensorRT-LLM (2026-10-25)

Purpose: read the actual pinned engine source before writing the M6 frozen-int8-base/LoRA format. This is a source
audit, not a benchmark and not a numerical-equivalence claim. No engine source is copied into the runtime. The
M6 format keeps its own versioned identity and is tested against an independent rational oracle.

Source-only statements below describe the exact commits/files in
[the evidence index](evidence/2026-10-25-engine-source-audit/SOURCE-INDEX.md). TensorRT-LLM was not installed or
executed; its speed, cross-GPU equality and model quality are unknown here.

## Pinned sources

| Engine | Identity used here | How read | Scope limit |
| --- | --- | --- | --- |
| vLLM | `e7473bf6862289f0647d1f4b01498288b181e063` | read-only sparse clone, `git show HEAD:<path>` | the measured vLLM 0.32.0 install is a separate build; this pin is not proven byte-identical to it |
| SGLang | installed wheel `0.5.22` in a scratch venv | direct file reads, SHA-256 recorded | the installer records no upstream commit; the audited files are pinned by hash, not by git commit |
| TensorRT-LLM | tag `v1.2.1` → commit `376f7e1bd8ed543f75014309e3fd4b237e9b0e73` | raw files fetched from the commit URL, SHA-256 recorded | source only; no install, run, profile or token comparison |

Measured engine behaviour already recorded in this repository is kept separate: [vLLM cross-GPU probe](evidence/2026-10-24-vllm-probe/README.md),
[SGLang cross-GPU probe](evidence/2026-10-24-sglang-probe/README.md), and the [same-workload throughput comparison](strict-vllm-comparison-2026-10-25.md).
Those receipts are not evidence for the source claims above, and vice versa.

## vLLM

### W8A8 integer projection

The compressed-tensors W8A8-int8 scheme stores a per-output-channel FP32 weight scale (`(N, 1)`) and supports a
dynamic per-token activation scale. After loading, the CUTLASS kernel requires the weight transposed, so the module
does it once and replaces the parameter (`weight.t()`); there is no per-request transpose
([cutlass.py:46-56](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/kernels/linear/scaled_mm/cutlass.py#L46-L56),
[weight scale:71-83](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/layers/quantization/compressed_tensors/schemes/compressed_tensors_w8a8_int8.py#L71-L83)).

The dynamic quantizer computes one row maximum, writes `scale = absmax / 127`, and converts with the PTX instruction
`cvt.rni.sat.s8.f32` (`rn` = round to nearest even, `sat` = saturate). An all-zero row uses reciprocal scale zero
([scaled_quant.cu:10-37](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/csrc/quantization/w8a8/int8/scaled_quant.cu#L10-L37),
[scaled_quant.cu:142-177](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/csrc/quantization/w8a8/int8/scaled_quant.cu#L142-L177)).
The integer GEMM result is scaled in a FP32 epilogue: the documented algebra is `D = s_a s_b D_hat + bias`, with
symmetric weights only and symmetric/asymmetric activations (`s_a` and optional zero point)
([Epilogues.md:22-67](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/csrc/quantization/w8a8/cutlass/Epilogues.md#L22-L67)).
The output dtype is the activation dtype, so the final store is FP16/BF16 when the layer runs in FP16/BF16
([cutlass.py:122-154](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/kernels/linear/scaled_mm/cutlass.py#L122-L154)).

### Weight-only and batch invariance

The W8A16/Marlin path repacks both quantized weights and scales once after loading (`gptq_marlin_repack`,
`marlin_permute_scales`) rather than at each forward
([marlin.py:100-143](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/kernels/linear/mixed_precision/marlin.py#L100-L143)).
The source states explicitly that Marlin chooses tiling and K-split from the token count, so its result depends on
batch size; batch-invariant mode keeps the checkpoint layout, unpacks the weight and uses the batch-invariant matmul
instead (`compressed_tensors_wNa16.py:79-82`). That fallback accumulates in FP32 with `tl.dot` and a persistent
M/N tile order, not an integer dot
([batch_invariant.py:100-137](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/determinism/batch_invariant.py#L100-L137)).

### LoRA placement

The synchronous path computes the base layer first and then adds the adapter result into that output
(`base_linear.py:215-232`). The optional dual-stream path runs the quantized base GEMM on the default stream and the
Punica shrink/expand branch on an auxiliary stream using the same original `x`; the join is `output.add_(lora_result)`
(`base_linear.py:256-300`). The adapter branch never consumes the quantized activation, and the base output remains
the destination. The add happens in the output dtype (FP16/BF16).

## SGLang

### W8A8 integer projection

SGLang 0.5.22 documents W8A8-int8 as static per-channel symmetric weights and dynamic per-token symmetric
activations (`sglang/srt/layers/quantization/w8a8_int8.py:64-69`).
The per-token Triton quantizer floors the row maximum at `1e-10`, computes `absmax / 127`, and rounds with
`libdevice.round`, not the `cvt.rni` conversion used by vLLM
(`sglang/kernels/ops/quantization/int8_kernel.py:21-55`).
CUDA `__nv_roundf` follows C `roundf` semantics, where halfway cases go away from zero, so the tie rule differs from
vLLM even before any tile-order question. The projection itself calls `sgl_kernel.int8_scaled_mm` with
`out_dtype=x.dtype` (`sglang/srt/layers/quantization/w8a8_int8.py:224-231`).

The separate blockwise-int8 Triton kernel applies a weight scale and an activation scale per K block:
`accumulator += tl.dot(a, b).to(tl.float32) * a_s * b_s` (`sglang/kernels/ops/gemm/int8_kernel.py:73-85`).
This is a block-dependent rounding tree; changing the block size changes the result. It is not the same contract as one
exact integer dot followed by one final encoding.

### LoRA placement

The wrapper applies `base_layer.quant_method.apply(...)` to the original input, then calls `apply_lora(base_output, x)`
with the same input (`sglang/srt/lora/layers.py:482-509`).
The experimental TRT-LLM-derived path overlaps only the LoRA-A shrink with the base QKV GEMM on a side stream; the
expand waits for the rejoin and reads both the shrink intermediate and the base output
(`sglang/srt/lora/trtllm_lora_temp/attention.py:31-75`).
The placement is the same as vLLM: base first, adapter delta added at the output.

### Measured caveat

Stock 0.5.22 differed on 14 of 208 prompts between the 5070 Ti and the 3060; the deterministic patched build still
differed on 2 of 32 compared prompts. The source explains why the engine does not promise a portable identity
(runtime quantization, block/tile-dependent reductions), but this audit did not isolate which instruction or tile
caused those specific token differences. See [the SGLang probe](evidence/2026-10-24-sglang-probe/README.md).

## TensorRT-LLM (source only)

### Modes and weight-only storage

`QuantAlgo` names `W8A16`, `W4A16`, and the `W8A8_SQ_*` plugin variants with per-channel or per-tensor weights and
per-token or per-tensor activations (`tensorrt_llm/quantization/mode.py:23-56`).
`WeightOnlyQuantLinearMethod.create_weights` stores a `(in_features, out_features)` int8 weight and one scale per
output channel, and `apply` calls `torch.ops.trtllm.weight_only_quant_gemm` with that scale
(`tensorrt_llm/_torch/modules/linear.py:1499-1532`). During loading, the helper transposes the checkpoint weight to
int8 and runs `preprocess_weights_for_mixed_gemm` on the CPU before copying it to the module
(`tensorrt_llm/_torch/modules/linear.py:156-166`). The mixed GEMM is the `fpA_intB` CUTLASS family
(`cpp/tensorrt_llm/kernels/cutlass_kernels/fpA_intB_gemm/fpA_intB_gemm_template.h:60-98`); the layout transform is
selected for the dequantizing mixed-MMA operator (`OpMultiplyAddDequantizeInterleavedBToA`) in
`cutlass_preprocessors.cpp:98`. There is no full FP16 weight shadow in the module, but the engine does materialize a
packed int8 layout once at load.

That preprocessing is not numerically neutral. On the non-SM100 path it transposes, interleaves and adds 128 to every
stored int8 value, turning the signed representation into a biased byte for the unsigned MMA input
(`cpp/tensorrt_llm/kernels/cutlass_kernels/cutlass_preprocessors.cpp:418-438,570-628`). The host symmetric quantizer
uses C `round()` (halfway away from zero) and clips to `[-128, 127]`, not RNE
(`cutlass_preprocessors.cpp:735-741`). These are engine-internal choices, not a contract we can copy.

### W8A8-SQ kernel

The `int8_sq` kernel uses `__dp4a` for four int8 products per instruction, keeps an int32 accumulator per output, and
applies a per-channel and/or per-token FP32 scale when writing the output
(`cpp/tensorrt_llm/kernels/weightOnlyBatchedGemv/int8SQ.cu:26-27,63-64,98-120`). It dispatches a small-M CUDA-core
tactic separately from the tensor-core GEMM (`int8SQ.cu:134-166`). Activation quantization uses a row maximum floored
at `1e-6`, `scale = max / 127`, a reciprocal multiply and `cvt.rni.sat.s8.f32`
(`cpp/tensorrt_llm/kernels/quantization.cuh:222,248-253,265-271`;
`cpp/tensorrt_llm/common/cudaTypeUtils.cuh:366-375`). So TensorRT-LLM's activation rounding is ties-even like vLLM,
while its host weight quantization is ties-away like neither of our candidate rules.

### LoRA placement

The Python linear layer computes the base matmul first, then adds `self.lora(...)` to that result
(`cpp`-facing `tensorrt_llm/layers/linear.py:226-269`), and the PyTorch module's `apply_linear` does
`output = quant_method.apply(...)`, then `output = output + lora_result` (`_torch/modules/linear.py:2266-2276`).
The LoRA kernel runs a grouped GEMM; the first (shrink) GEMM uses split-K over the hidden dimension with
`mSplitKSlices = 16` (`cpp/tensorrt_llm/kernels/lora/lora.cpp:323-330`;
`cpp/tensorrt_llm/kernels/lora/lora.h:67`). The split-K reduction is a numeric-order choice that our identity must not
inherit.

## Cross-engine comparison and M6 decision

| Mechanism | vLLM | SGLang 0.5.22 | TensorRT-LLM v1.2.1 | M6 decision |
| --- | --- | --- | --- | --- |
| Frozen weight storage | int8 checkpoint, per-channel scale | int8 checkpoint, per-channel scale | int8 checkpoint, per-output scale | store signed int8 `[N,K]` plus FP32 per-output scale in the artifact |
| Weight prepack | transpose once at load | engine-specific layout at load | transpose/interleave/+128 at load | prepack once at artifact creation; no runtime transpose or quantization |
| Activation scale | dynamic per-token `absmax/127` | dynamic per-token `absmax/127` | dynamic per-token `max/127` | keep the existing B22 power-of-two row exponent; do not copy `absmax/127` |
| Activation rounding | `cvt.rni.sat.s8.f32` | `libdevice.round` | `cvt.rni.sat.s8.f32` | exact integer RNE against a rational scale |
| Dot | int8 GEMM, FP32 epilogue | CUTLASS int8 or blockwise Triton with per-block FP32 scales | `__dp4a` int32 or mixed GEMM | one exact integer dot; three limb products because only the weight is int8 |
| Output composition | bias/scale in FP32, store in activation dtype | scale in FP32, store in activation dtype | FP32 scale, store in output dtype | one explicitly specified FP32 encoding; no approximate float scale |
| LoRA | base output + Punica delta | base output + delta | base output + LoRA | base projection + adapter delta; adapter reads the original activation |
| Batch/tile dependence | Marlin is batch-dependent; batch-invariant path bypasses it | blockwise path is block-dependent | split-K=16 for LoRA shrink | fixed K order, no batch-dependent dispatch, no split-K sum |
| Portability evidence | 15/208 prompts differ across GPUs in batch-invariant mode | 14/208 stock, 2/32 patched | not measured | must be proven by our own SM86/SM120 tests |

The engines agree on the architecture that matters for M6: a quantized frozen base GEMM, a separate adapter branch
that reads the original activation, and an add at the output. They do not agree on a portable arithmetic identity, and
none of them provides one across the two GPU architectures in the recorded probes. The M6 operator therefore adopts
the placement, not the arithmetic.

## M6 design constraints derived from the audit

These are proposed constraints for the next implementation. They are not implemented, tested, selected or accepted.

1. **Artifact, not runtime quantization.** Quantize on the host from the pinned parent weights with the independent
   rational oracle. The artifact carries the int8 rows, FP32 scales, logical/padded shapes, format version, quantizer
   version, parent file hashes and a canonical SHA-256. Runtime code only loads and verifies; it never re-quantizes a
   weight or silently falls back to FP16.
2. **One prepacked layout.** Store each output row's int8 weights contiguous over K, matching the column-major B
   operand of the existing signed-int8 MMA path. Padding is canonical (zero weights, named logical shape) and part of
   the artifact hash. This replaces the per-request transpose/interleave that the engines do at load.
3. **Keep B22 exact.** The activation exponent remains a per-row power of two, so the activation scale is exact and
   independent of batch, tile and GPU. Do not replace it with `absmax/127` or with an engine's per-block FP32 scale.
   With one int8 weight operand, each dot needs three limb products, not the nine of the B22-by-B22 path. This is a
   work-count reduction, not a measured speed claim.
4. **Bounded integer accumulation.** Each signed-int8 limb product is bounded by `127 * 128 * K`; for the admitted
   `K <= 32768` this is below `2^29`, so int32 accumulation is exact. Reconstruct the full dot in int64. With a
   `[-127,127]` weight and a B22 activation the bound is below `127 * 2^22 * 2^15 < 2^44`, leaving ample int64
   headroom. Prove the bound in code and tests; do not rely on a comment.
5. **Two-limb final encoding.** The exact value is `S * scale_significand * 2^e`. With a 24-bit FP32 scale
   significand and `|S| < 2^44`, the product can reach just under `2^68`, beyond int64. Encode it with a two-limb
   (96-bit) integer on CUDA and arbitrary-precision integers on the CPU oracle, then round once to FP32 with the
   specified RNE/FTZ rule. Never multiply an int64 dot by an FP32 scale and call the result exact. Test the `2^63`
   boundary, exponent carry, subnormal flushing and overflow rejection explicitly.
6. **Composition is part of the identity.** The base projection publishes the same exact FP32 value as the existing
   integer reference, the adapter branch computes from the original activation, and the delta is added with one named
   rounding step before the graph's normal FP16 publication. Do not copy the engines' FP16 epilogue add as if it were
   the strict contract.
7. **Only adapters are trainable.** Base weights are immutable buffers/artifact entries with `requires_grad=False`;
   there is no dequantized FP16 `.weight` materialization. The graph validator and LoRA loader currently require FP16
   base parameters, so they must be extended explicitly for this format, not bypassed. Tied storage stays tied, and
   the adapter perturb/update/replay/restore path stays the canonical one.
8. **Batch invariance is a gate, not an optimization.** The kernel must produce the same value for the same row
   regardless of batch size, row position, output tile, chunking or GPU. Fixed K order, deterministic partial
   reductions and no split-K sum. Test batch/permutation/chunk equality and cross-GPU equality before any graph
   integration or performance claim.
9. **Measure after the proof.** First the independent CPU oracle and boundary tests, then the versioned CUDA operator
   on non-model widths (768/1024/2048/4096) on SM86 and SM120, then graph integration, then the three trained models
   with parent and perturbed adapters. Report operator time separately from wall time. A three-limb dot is not
   expected to match a one-limb vendor W8A8 kernel; no throughput promise follows from the source audit.

## What this audit does NOT show

- No TensorRT-LLM installation, kernel run, profile, token comparison or speed result. Its mechanisms are source-only.
- No proof that the pinned vLLM source is the exact build measured in the 2026-10-24 probe, and no proof that the
  SGLang wheel matches an upstream commit. The evidence index pins the files that were actually read by hash.
- No claim that vLLM, SGLang and TensorRT-LLM are numerically equivalent to each other. They use different rounding,
  scaling, tiling and split-K choices; the recorded cross-GPU token differences already disprove a portable identity
  for the tested builds.
- No model quality, learning, ES sensitivity, throughput or acceptance result for the M6 format.
- No change to the approved M0–M6 objective, the frozen recipe/noise/ES/ledger/generation-record contracts, or the
  plan SHA-256 `4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.

The exact files, commits, URLs and file hashes are in
[the source index](evidence/2026-10-25-engine-source-audit/SOURCE-INDEX.md); the read-only method and its limits are
in [the evidence README](evidence/2026-10-25-engine-source-audit/README.md).
