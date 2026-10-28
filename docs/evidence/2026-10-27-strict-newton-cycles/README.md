# Reject shortening Newton iteration counts, 2026-10-27

Hypothesis: the original FP32 recurrence might enter a two-cycle early enough that reciprocal 3 steps
equals 5, and rsqrt 4 equals 6. This is **false** for the frozen operation sequences.

The probe adapts the earlier [normal-domain checker](../2026-10-27-strict-normal-domain/README.md),
using explicit RNE operations and retaining the original functions as independent comparison paths.
Only the proposed fast branches' iteration counts change. Every **1,671,934,059** positive FP32 input
encoding in the admitted `[DOMAIN_LOW,DOMAIN_HIGH]` interval is evaluated on the local SM120 GPU.

`raw/diagnose-01.json` records:

- Reciprocal 3 vs 5 steps: **236,645,051** bit differences.
- Rsqrt 4 vs 6 steps: **25,844,821** bit differences.
- Either function differs on **257,673,297** inputs; failure flags agree, and no removed node check sees
  a subnormal/nonfinite intermediate. These facts do not make the different finite results acceptable.

`raw/exhaust-01.log` is the first checker correctly failing its zero-mismatch assertion. The diagnostic
variant records per-function counts and explicitly reports `completed_diagnostic_with_mismatches`;
it is not an acceptance pass. The copied edge/composition tests are retained as harness context, not
claimed as executed/passing for these shortened recurrences. No speed benchmark is warranted.

## What this does NOT show

No valid arithmetic optimization, selected source change, cross-GPU/native proof, quality tolerance,
learning result or 80% result is established. Preserve the original five/six iterations. The selected
runtime, flags and numerical contract remain unchanged; no deployment or lab state changed.
