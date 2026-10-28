# Guarded normal QK score trees, 2026-10-27

Unselected SM120 follow-on to [normal-domain nonlinear nodes](../2026-10-27-strict-normal-domain/README.md),
against selected runtime `0eb86cb9`. No arithmetic precision, reduction order or compiler audit is changed.

## Exactness argument and scope

After the original checked/flushed loads, guard every Q/K operand in a CTA: it must be signed zero or
have magnitude in `[2^-30,2^20]`. Every admitted operand is an integer multiple of `2^-53`; every exact
product is on the `2^-106` lattice. Each rounded product and tree sum remains on that lattice. Nonzero
nodes therefore have magnitude at least `2^-106`, above the smallest normal. With at most 256 channels,
absolute tree sums are at most `2^48`, below overflow. Removing intermediate flush/classification from
this **QK tree only** cannot change its rounded nodes or flags. Signed-zero operations still use the same
explicit RNE add/multiply instructions.

Score scaling, softmax, weighted V trees and all original Q/K/V loads retain their checks. Invalid or
out-of-range operands select the original checked score tree. All masked loads remain checked. A shared
sticky unsafe bit selects one CTA-uniform branch; GQA checks each staged key tile, while prefill checks
its staged plane. Earlier admitted GQA tiles remain safe if a later tile forces fallback.

This proof concerns the actual guarded trees, not a blanket assumption that trained-model activations
are safe. In particular, summing tiny products without their per-node flush can change results; the test
uses a large final scale to make that otherwise tiny difference observable.

## Checks and screening

`raw/tests-04.log`: **36 passing** cases on the final helper: normal inputs, tiny-product fallback,
large/overflowing inputs, signed zeros and masked nonfinite values; both decode and prefill, key tails,
and a fused-quantization source-composition regression. Output bits and deferred failure flags match the
original implementation. The first helper attempts failed source-replacement assertions (and initially
used an invalid span prefix); those receipts are retained, not counted as passes.

`raw/mutation-01.log`: the seven tiny-product cases pass on the control; **2/2 mutants are killed**:
bypassing the guard changes observable results, and hardware FTZ is rejected by the unchanged instruction audit.

The final-source five-sample parent-inference pilot (`raw/full-pilot-02.json`) gives Qwen batch 32:
**9895.9 token/s short32**, **9936.8 chat128**, with identical selected-control token hashes. Nearby frozen
controls are about **9868 / 9886**; this is not matched ABAB evidence of a robust gain. The pilot does not
justify selection. Full request time includes the range guard and original fallback code. Runtime remains
unchanged. `full-pilot-01.log` is a failed source-composition attempt, not a performance result.

## What this does NOT show

No 80% result, production selection, full production acceptance, portable/trained cross-host parity,
native Windows/SM86 qualification, arbitrary attention layouts, package/resource acceptance or learning
effect is established. No deployment or lab-state change occurred. Finite tests do not exhaust every
Q/K bit pattern or every thread mapping; broader coverage would be required before promotion.
