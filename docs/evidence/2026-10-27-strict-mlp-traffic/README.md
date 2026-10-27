# Gate/up handoff traffic screening, 2026-10-27

Unselected SM120 probe against `0eb86cb9`. Force gate/up GEMM to split-K one, publish its original exact
B22 encoded FP32 values, then apply the original strict SiLU/gate and per-row maximum in a tiled finish,
followed by the unchanged packing kernel. This avoids int64 partial materialization and re-reading; it
also changes projection parallelism. There is no precision change, approximate SiLU or FP32 dot product.

`raw/tests-02.log`: **6 passing** projection/SiLU/packed-plane cases, both bias modes, real Qwen gate/up
shape and tails. Small cases also compare with independent CPU B22 projections and strict CPU nonlinear
operations. Planes/exponents and monotonic failure flags match. The initial CPU oracle call used a
nonexistent combined helper; that failed receipt is retained separately from the passing retry.

The five-sample full-request pilot (`raw/full-pilot-01.json`) preserves Qwen batch-32 token hashes but
gives **9536.3 token/s short32**, **9538.7 chat128**. Nearby frozen controls are about 9868 / 9886. This
is sufficient to reject the simple S1 handoff; no matched ABAB speedup claim is made. The experiment
does not isolate the cost of changed parallelism from traffic or epilogue scheduling.

**Reject this implementation.** Removing partial traffic alone does not imply a faster MLP. Any later
paired-operand or differently scheduled implementation must demonstrate its own whole-request benefit.
The selected runtime remains unchanged.

## What this does NOT show

No faster selected decoder, 80% result, complete failure/edge/mutation qualification, trained candidate
cross-host parity, native Windows/SM86 acceptance, package/resource qualification or learning effect is
established. This parent-inference pilot does not qualify arbitrary models or replacement Parameters.
No deployment or lab-state change occurred.
