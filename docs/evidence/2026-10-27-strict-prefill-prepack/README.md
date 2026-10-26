# Bounded B22 prefill weight packing: rejected

This is a different scheduling strategy for the **same** B22 integer dot: quantize one projection's live
FP16 weights into three byte planes once, reuse those planes across prefill M tiles, then release the
scratch. The largest measured scratch is 3 × 896 × 9728 = 26,148,864 bytes. No full-model integer copy is
retained. The original source at `eebf689f` is the control; the prototype does not ship in the runtime.

Test-first collection fails before the prototype exists (`red-01.log`). Three GPU cases subsequently pass
bit comparisons against both original CUDA projection and independent CPU oracle, including live in-place
changes and zero weights (`tests-02.log`). They cover K=64/896/4864, 65 rows and column tails. This is finite
operator coverage, not decoder/platform acceptance.

The first build is rejected by the existing SASS auditor: NVRTC computes a variable-stride loop's trip
count with MUFU.RCP. Its source, cubin and disassembly are preserved as `rejected-01*`. A fixed 128-thread
loop stride removes that instruction; audits are still enforced. No audit was disabled.

Packing cost is included in graph-replayed microbenchmarks (eight calls per replay, nine samples). At 888
rows, the MLP gate/up shape K=896/N=9728 takes approximately **470 µs** with original streamed half weights,
versus **588 µs** with packed weights and M64/N32 tiles. M64/N64 is **1091 µs**. M32 packing also loses on
the main MLP shape. Results at 1024 rows and the other projection dimensions are in `raw/bench*.json`.
The larger shared-memory footprint and extra plane traffic eliminate the hoped-for conversion savings.
No end-to-end implementation is selected; stop this direction at the operator gate.

## What this does NOT show

These probes do not establish a mathematical impossibility of packing, a universal memory ceiling, a
decoder speedup, quality, other hardware support or managed/native acceptance. They preserve the tested
B22 results; there is no change to precision, historical recipe or production default.
