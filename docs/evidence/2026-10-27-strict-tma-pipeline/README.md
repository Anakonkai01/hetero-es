# Exact B22 TMA pipeline prototype, 2026-10-27

Unselected research against runtime `0eb86cb9`, on the local RTX 5070 Ti / SM120. The selected
runtime is unchanged. This continues the [initial TMA transport proof](../2026-10-27-strict-tma/README.md).

## Transport and numerical checks

The prototype replaces only streamed GEMM operand transport. Weight tiles use 128-byte swizzling;
activation tiles use 64-byte swizzling and a rank-three map separating radix planes, including row tails.
Two/three-stage ring buffers use transaction barriers with phase reuse. The original nine integer MMAs,
degree accumulation, int64 reconstruction, RNE encoding, bias and split finish are retained.

- `tests-01.log`: **10 passing** copy/pipeline cases, including tails, independent planes and barrier reuse.
- `mma-tests-01.log`: **9 passing** cases: eight independent CPU B22 oracle cases (each checks both column
  tiles and three splits) and an instruction-policy test. Includes empty splits, FP16 extremes and bias.
- `byvalue-tests-01.log`: **5 passing** by-value cases, including capture/replay, changing live values and restore.
- `prefill-tests-01.log`: **2 passing** adapter cases, including residuals and monotonic deferred flags.

The exact memory opcode `FENCE.VIEW.ASYNC.S` is admitted by the **prototype's** SASS audit; all other
integer-policy checks remain. PTX audits are unchanged. This does not grant a general FENCE/FTZ/FMA exception.
The bounded barrier timeout sets a private infrastructure bit (4); this is not a qualified product error ABI.

V1 stores maps on the GPU; V2 passes aligned 128-byte maps as `const __grid_constant__` parameters,
as described in NVIDIA's [CUDA programming guide](https://docs.nvidia.com/cuda/archive/13.1.1/cuda-programming-guide/04-special-topics/async-copies.html).
V2 has no per-projection GPU descriptor upload. Host map encoding and parameter construction remain in
the full-request measurements. Map contents describe live addresses/layouts, not cached weight values.

## Measurements

`raw/operators-01.json` records warm and explicitly L2-evicted graph measurements, descriptor setup,
registers/shared memory/residency and compiler audits. Prefill M888/K896/N4864 falls from **240.17 to
225.33 µs**, M888/K4864/N896 from **243.46 to 227.94 µs** (two stages, three resident CTAs).
Three stages are slower. Decode warm improvements are modest and some cold cases regress. These V1
core timings reuse descriptors; their approximately **150–203 µs** setup is reported separately.

V2 prefill-only full-request ABAB controls (`raw/full-{base,tma}-{a,b}.json`), mean of two medians:

| Case | Baseline token/s | TMA token/s | Change |
| --- | ---: | ---: | ---: |
| Qwen short32, batch 32 | 9868.37 | 9961.77 | +0.946% |
| Qwen chat128, batch 32 | 9885.65 | 9979.23 | +0.947% |

Five timed repetitions per case/process, one warmup, synchronized host wall time, same prompt/token
budgets as the selected control. All token hashes agree (`bc4a5504e37c…`, `a9fad5ca48ed…`). Each TMA
process records **2016** intercepted projections. Prefix reuse and EOS stopping remain disabled.
Full reports retain the underlying runtime fingerprint and separately identify/hash the unselected adapter.

**Decision:** park this implementation. The approximately 1% full-request gain does not justify promoting
a new architecture-specific transport before finding a stronger whole-path gain. The approximately 6–7%
operator improvement must not be presented as a 6–7% decoder improvement.

## What this does NOT show

No 80%-vLLM result, production TMA selection, complete failure ABI, mutation acceptance, trained candidate
cross-host parity, SM86/native Windows qualification, package/resource admission or managed lifecycle is
established. Grouped decode/fused consumers were not replaced. No deployment, lab-state change or learning
run occurred. Initial collection failures are retained as failed receipts, not counted as passes.
