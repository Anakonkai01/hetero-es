# Prefill GEMM occupancy, batched weight exponents, rejected pilots and lm_head bound feasibility — 2026-10-27

Runtime commit `7ca91112` (base `a7884392`, runtime identical to `2eb4da0d`/`6cc69d26`). Branch
`work/codex-frozen-perf-2026-10-25`. 5070 Ti only. This is a **partial** checkpoint written at the owner's request
to hand off to Codex; the gates listed under "What this does NOT show" are still open.

## Selected change (`7ca91112`)

1. **Prefill projections (64-column stream kernel only):** `STAGES=2` and `__launch_bounds__(128, 3)`
   (`PREFILL_STAGES`, `PREFILL_MIN_BLOCKS` in `integer_cuda.py`). 168 registers, 28 KiB shared memory, three
   CTAs per SM instead of two. Decode (32-column) kernels are compiled exactly as before. Only the pipeline
   depth/occupancy changes; every integer sum and encoding is unchanged.
   Operator (888 rows, warm): 896x9728 546 -> 496-499 us, 896x1152 74 -> 68 us, 896x896 57 -> 54 us,
   4864x896 unchanged (~257 us). Other tried settings: 64 cols + min-blocks 4 (128 regs) 507 us; 32 cols with
   4-5 CTAs/SM 525-532 us; 8 or 16 warps per CTA slower; 4 stages exceed 48 KiB static shared memory.
2. **Request weight exponents in one launch:** `integer_weights_batched` (one warp per row, 16-byte loads,
   binary search of a call-local table of (weight, exponents, rows, width)). Same order-independent maximum,
   exponent formula and nonfinite flag as `integer_weights`. Weights whose rows are not 16-byte multiples or
   whose pointer is not 16-byte aligned keep the per-weight kernel. `_end_request` clears with one
   `torch._foreach_zero_` instead of 169 launches. Prefill (1-token generation) wall 39.1 -> 36.4-37.0 ms.

Tests: `tests/eval/test_integer_weights_batched.py` (12 GPU tests: equality with the per-weight kernel on 36
matrices incl. zero/subnormal/max-half rows, Inf/-Inf/NaN flags at three positions, routing of narrow and
8-byte-offset weights to the per-weight kernel, cleared buffers). `test_integer_decoder.py` counting test now
counts both refresh paths. Targeted GPU suites `test_integer_{decoder,cuda,stream,group,fused_finish,
packed_input,plan}.py`: **249 passed** on the 5070 Ti with the change.

## Whole-generation measurement (separate processes, ABAB, `harness/ab.sh`)

`raw/{base,new}-{a,b}.json` from the sealed `bench_single.py` (median of five warm samples per process):

| Case | Base `a7884392` | `7ca91112` | Gain | Token hash |
| --- | ---: | ---: | ---: | --- |
| Qwen short32 | 8899.0 / 8927.4 | 9177.3 / 9131.9 | +2.7% | `bc4a5504e37c` both |
| Qwen chat128 | 9111.5 / 9102.4 | 9240.1 / 9240.6 | +1.5% | `a9fad5ca48ed` both |

Qwen short32 is about 66% of the vLLM control (13835). The goal is not achieved.

## Measured diagnosis used by the handoff (5070 Ti, Qwen B32)

- Decode step ~2.47 ms (325 kernels): integer GEMMs ~1.6 ms, attention 0.37 ms at short32 (0.78 ms at the
  end of chat128), RMS/finish/pack/input/greedy ~0.48 ms. lm_head alone ~355 us (272 MB FP16 read; floor 322).
- `imma_peak.py`: m16n8k32 int8 reaches 386-396 TOPS with the B22 9-product pattern at 12-32 warps/SM.
- Decode GEMM gate/up (896x9728, 32 rows) takes ~24.6 us even with weights warm in L2 -> it is MMA/issue bound,
  not DRAM bound (DRAM floor 20.6 us). In-loop cycle counters (`gemm_prof.py`) show ~80% of IMMA peak inside the
  K loop; the rest is wave quantization and per-CTA ramp. Ablations (`EXP_NO*` in the scratch copy): no weight
  conversion 23.7 us, no cp.async loads 21.4, no MMA 19.3.
- Kernel boundary inside a CUDA graph costs ~0.7 us (`launch_cost` measurement); glue kernels are 1.6-2.1 us.
- Decode attention time is set by the longest row (one CTA per sequence and KV head walks ~0.1 us/key).

## Rejected pilots (sources/diffs in `rejected/`, nothing selected)

| Pilot | Result |
| --- | --- |
| L2 prefetch of o/gate/up weights from a side stream during attention (`prefetch_exp.py`) | gate/up 4.3 us faster per layer, but attention slowed and the prefetch kernel cost more: step 2496 -> 2529-2689 us |
| Prefetching each CTA's own K/V rows to L2 inside `strict_attention_gqa` | attention 377 -> 428 us/step |
| Key-split decode attention: 32-key chunk CTAs, last-CTA softmax and in-order root combine (`strict_keysplit_cuda.py`, bit-equal to `strict_attention`) | short32 370 vs 378 us/step; chat128 end 701 vs 775 us/step; whole generation +0.3-0.6% -> not worth the complexity |
| Root-only nonfinite checks inside the dot trees (proof: a nonfinite operand of add/mul stays nonfinite) | no measurable gain in the key-split kernels |
| Fusing finish_residual with the next strict_rms_quant (one CTA per row) | 0.7-0.9 us slower per call than the two kernels |
| Persistent decode GEMM (same items, one pipeline fill per CTA, next-item exponents prefetched) | gate/up 22.2 -> 22.3 us, down s8 13.1 -> 15.4 us |
| Decode GEMM with 8/16 warps per CTA, 2 or 4 stages, other min-block bounds | no gain or slower |

## lm_head exact-argmax bound feasibility (`lmhead-feasibility/`)

744 final-normed hidden states of Qwen (HF FP32 forward, 8 short prompts and 16 chat rows x 32 greedy steps),
B22 row quantization in float64 (exact). Weights truncated to 7 signed bits per element:
`t = floor(qw / 2^15)`, `approx = 2^15 * sum(qa * t) + 2^14 * sum(qa)`, rigorous bound `2^14 * sum|qa|`.
Output (`output.txt`): surviving 32-token tiles per row median **1**, mean **1.94**, max **13** of 4748; the
true argmax always survives. This is the design input for the handoff's next step, not an implemented speedup.

## What this does NOT show

- No 3060 WSL2 or native Windows run, no mutation run, no trained parent/±/restore parity, no check-all and no
  packaging check of `7ca91112`. Only the 5070 Ti targeted suites above and the ABAB token hashes.
- The prefill occupancy setting was tuned on SM120 only; SM86/SM75 timing is unmeasured.
- The rejected numbers are single-process operator/step measurements, not sealed acceptance evidence.
- The lm_head feasibility uses HF FP32 hidden states, not strict-engine states, and no kernel exists yet.
