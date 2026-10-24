# Strict CUDA kernels for the ADR-012 reference (2026-10-24)

Source: `runtime/src/heteroes/eval/strict_cuda.py` (NVRTC kernels: linear, RMSNorm, residual add, SiLU gate,
RoPE, attention/softmax), `runtime/src/heteroes/eval/qwen2_strict_cuda.py` (Qwen2 graph on those kernels),
`runtime/scripts/probe_strict_backend.py` (cross-machine probe), `runtime/scripts/compare_strict_receipts.py`.
Branch `fix/human-review-single-model-2026-10-24`. Backend identity `qwen2_pairwise_f32_cuda_v1_experimental`,
`hardwareQualified: false`.

## Why the kernels should give the same bits as the eager reference

- Every FP32 add/multiply is inline PTX `add.rn.f32`/`mul.rn.f32`. The PTX ISA excludes instructions with an
  explicit rounding modifier from multiply-add contraction; NVRTC also runs with `--fmad=false --ftz=false`.
  Subnormal results are flushed to signed zero by integer bit selection, as the reference does.
- The linear tree: the reference adjacent-pair tree with odd-tail carry equals an aligned power-of-two tree
  padded with -0.0, because x + (-0) == x for every finite x under round-to-nearest; +0 padding would turn -0
  into +0. Threads reduce aligned blocks, a warp combines lanes with an xor butterfly (adjacent aligned pairs,
  commutative addition), and warps combine with the same padded tree. Runtime-length trees (RMSNorm, softmax
  denominator, attention dot products and PV sums) use a binary-counter stack folded from the lowest set bit,
  or an in-place stride tree with a barrier per level; both are the same tree. CPU emulations of all three
  forms are tested against `reference_ops.pairwise_sum`.
- Each build audits the PTX and (with Triton's `nvdisasm`) the SASS. Floating instructions must be rounded
  add/mul or exact operations: moves/loads, FP16->FP32 widening, comparisons, selection, the `HFMA2 -RZ, RZ`
  constant idiom, and, for the fused operations, floor, float<->int conversion of bounded integers and min/max.
  Runtime integer division was removed from the kernels because ptxas lowers it with `MUFU.RCP`.
- Nonfinite results and reciprocal/root/exp domain failures set a device flag, raised before logits return.

## Receipts

| File | What it records |
| --- | --- |
| `linear-tests-{nhan,nhut,thao,quang}-01.log` | Linear kernel tests, 112 passed on each GPU |
| `graph-tests-{nhut,thao,quang}-01.log`, `graph-tests-nhan-02.log` | Kernel + graph tests, 157 passed on each GPU |
| `graph-tests-nhan-01.log` | Earlier local run (153 tests), before the mutation-driven tests were added |
| `linear-mutation-01.log` / `-02.log` | 15/18 mutants killed at first; 18/18 after tests for subnormal inputs/products and -0 warp padding |
| `ops-mutation-01.log` / `-02.log` | 20/26 at first; 23/26 after tests for RMSNorm domain, subnormal inputs and inexact attention scale |
| `qwen-strict-{nhan,nhut,thao,quang}-01.json` (+ `.log`) | Pinned Qwen2.5-0.5B, parent + 8 antithetic candidates (seeds 7001..7004, sigma ±0.001) × 8 prompts × ≤64 tokens |
| `qwen-strict-comparison-01.json` | First comparison: flagged only the machine-local eager-check field, which only nhan has. Retained |
| `qwen-strict-comparison-02.json` | After excluding that diagnostic: **all four equal** (72 prompt cases, 4,387 tokens, weight/logits/text hashes, rewards) |

Machines: `nhan` (local RTX 5070 Ti, sm_120, Linux, driver 595), `nhut` (RTX 5070 Ti, sm_120, native Linux,
driver 580), `thao` and `quang` (RTX 3060, sm_86, WSL2, Windows driver 617.42). All four used NVRTC 13.2 and
torch 2.13.0+cu132. On nhan, the parent prefill logits of the first prompt equal the eager reference
(`eagerPrefillChecks`).

Three ops mutants survive. All three are equivalent:

- `exp-no-upper-domain`: every caller passes x ≤ 0 (SiLU uses -|x|; softmax shifts by the maximum, and rounding
  is monotone), so the upper-domain branch cannot be reached.
- `rsqrt-reassociated`: multiplying by 0.5 is exact in the normal range, and inputs in [1e-30, 1e30] keep r away
  from underflow/overflow. So (0.5·r)·t and 0.5·(r·t) round the same.
- `attention-negative-zero-max-kept`: exp(±0) gives identical bits and s + (±0) == s, so the reference's
  -0 → +0 normalization of the maximum does not change any output.

## Measured cost (host wall time, includes synchronization)

| Machine | Tokens/s per sequence (min–max over candidates) | Peak allocated / reserved |
| --- | --- | --- |
| nhan 5070 Ti | 58.1–64.2 | 1,077,519,872 / 1,153,433,600 B |
| nhut 5070 Ti | 61.5–62.4 | 1,076,912,128 / 1,153,433,600 B |
| thao 3060 | 23.0–25.8 | 1,076,912,128 / 1,153,433,600 B |
| quang 3060 | 21.6–24.4 | 1,076,912,128 / 1,153,433,600 B |

Live FP16 weights and buffers: 988,065,920 B. The eager reference took 46–149 s per token on these GPUs
(`../2026-10-24-human-review/reference-summary.md`). The lower nhan figures include the eager check and
other local GPU activity. Microbenchmarks during development were 2–3× slower than vendor FP16 for decode
projections and linear in rows for prefill: the kernel has no multi-row reuse yet.

## What this does NOT show

- No native Windows run: thao/quang are WSL2 using the Windows driver. Only two NVIDIA architectures
  (Blackwell sm_120, Ampere sm_86) and one NVRTC version were tested. No Turing/Ada.
- 72 prompt cases on one model is a finite matrix. It does not show equality for every input, longer
  contexts (the probe limit was 512, the kernel limit is 4,096 keys) or other model families.
- The probe evaluates prompts one at a time. Batched/compacted multi-sequence execution is not implemented.
- Not integrated into the managed lifecycle, recipes, qualification, SDK/lab, worker packaging or
  cross-process GPU ownership. Not a quality, learning or throughput-acceptance result. No threshold was chosen.
- `nvdisasm` came from the Triton wheel in each environment. Windows environments may lack it; there the
  SASS audit records `unavailable` and only the PTX audit applies.
- Host wall timings are not CUDA kernel times, and the GPUs were not otherwise isolated.
