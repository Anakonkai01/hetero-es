# Prefill SiLU plus activation packing: rejected for short32

The existing packed decoder has a `_prefill_gated_project` hook. This pilot uses the already proved strict
SiLU/quantization kernel at that hook before the down projection, retaining B14/B22 arithmetic. Single-row
and width >12288 requests keep the existing route. The prototype patch and tests are in `harness/` and do
not ship in the runtime.

The first test attempt calls a nonexistent CPU helper; that setup failure is preserved in `red-01.log`.
After correcting the oracle to `mul(silu(gate), up)`, the meaningful red run has **2 failures/5 passes**:
eligible cases do not yet use the fused route. The implementation then passes all **7 tests**. Tests compare
bits to the independent CPU oracle under in-place weight changes, B14/B22, one row, a ragged 33-row batch,
large-width fallback and nonfinite flags.

ABAB whole Qwen B32 generation, two five-sample round medians, `eebf689f` as control:

| Case | Before token/s | Prototype token/s | Change |
| --- | ---: | ---: | ---: |
| short32 | 9684.1 | 9634.9 | -0.51% |
| chat128 | 9705.5 | 9710.7 | +0.05% |

Generated token hashes match. Reject this implementation: the primary short32 objective regresses, and
the tiny chat128 difference does not justify selecting it. Its runtime/test edits were removed after
preserving the patch, test source and receipts. Frozen source copies used for timing remain in scratch.

## What this does NOT show

Finite numerical tests do not establish arbitrary-model or cross-platform qualification. These timings
do not demonstrate a general limitation of fusion; they only reject this particular implementation.
No change to historical precision, managed backend selection or deployed process was made.
