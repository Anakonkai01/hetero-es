# Balanced exact-integer decode waves

Selected source: `0eb86cb9`. For eligible B22 streamed decode on **SM120 only**, choose split S in 1..8 to
minimize `ceil(column_tiles*S / resident_ctas) * ceil(K_tiles/S)`, with three resident CTAs per SM, subject
to the existing per-projection workspace cap. Default target 8, row tiles of 32 and K divisible by 16 are
required; all other configurations keep their previous planning. This changes exact integer scheduling,
not row scaling, quantization, sums, rounding, flags or numerical contract.

The original frozen prototype enables SM86 too. ABAB Qwen B32 controls on 5070 Ti improve short32 from
**9411.0 to 9565.4 token/s (+1.64%)**, chat128 **9560.3 to 9738.4 (+1.86%)**; token hashes match. WSL2/3060
short32 instead changes **3026.8 to 2989.3 (-1.24%)**, chat128 is essentially unchanged. The selected source
therefore retains the old SM86 plan. This architecture decision is covered by a CPU policy test.

Test-first red receipts are preserved. The selected implementation passes **47 targeted tests**: CPU
planning/cap/repeated-projection coverage, nonpower split integer oracles at K=16/1040/4864 for both B14/B22,
empty partitions/tails, and fused decode consumers. Nonpower split source-audit variants were also added
to the full suite. Complete combined-source/platform/mutation acceptance is tracked separately in
`2026-10-27-strict-combined-acceptance` and is not inferred from these pilot checks.

## What this does NOT show

This dimension-only cost model does not guarantee improvement on arbitrary shapes or hardware. The
primary target is still short32, not the faster long-output curve. No quality/learning, managed/native
installer acceptance, deployment or lab device-state change is established here.
