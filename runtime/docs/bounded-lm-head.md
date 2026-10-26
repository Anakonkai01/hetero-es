# Exact bounded greedy selection for B22

`integer_lm_head.py` changes the execution of greedy decode, while preserving the integer projection
arithmetic in ADR-012. It does not change forward/logit APIs or any historical recipe. Hardware
qualification remains false. The selected path requires B22, streamed projections, aligned widths
divisible by 16, at least two active rows, a vocabulary of at least 4096, no head bias and penalty 1.
Other cases use the existing full projection and greedy selector. The first prefill token also uses
the full projection.

## Integer intervals

For a decode row and vocabulary column, let `a[k]` and `w[k]` be their original B22 integer quanta,
with row exponents `ex` and `ew`. The full score is the existing RNE/FTZ encoding of
`S = sum(a[k] * w[k])` at scale `ex + ew - 42`.

At request entry, store `t[k] = floor(w[k] / 32768)` as signed bytes. Finite FP16 weight rows have
`-24 <= ew <= 15` and the resulting bytes are in `[-128, 127]`. Define

```
P = sum(a[k] * t[k])
Q = sum(a[k])
L = sum(abs(a[k]))
C = 32768 * P + 16384 * Q
b = 16384 * L
```

Since `0 <= w[k] - 32768*t[k] < 32768`, each residual from the midpoint is at most 16384 in
magnitude. The triangle inequality gives `C-b <= S <= C+b`. All sums use exact integers.

The kernel compares columns with different weight exponents on a common exponent of 15. For
`d = 15-ew`, compute `lower = floor((C-b)/2**d)` and `upper = ceil((C+b)/2**d)` using signed,
outward integer rounding. These are conservative bounds at the common scale `ex-27`.
RNE followed by signed-zero FTZ is monotone, so it is sufficient to encode the maximum lower and
upper integers of each 32-column tile. This avoids an encoding for every column. Outward rounding
can admit additional tiles; it cannot exclude a valid winner.

With width at most 32768 and B22 operands at most `2**22`, the original dot is at most `2**59` in
magnitude. The midpoint/radius bounds remain below `2**60`. Per-digit int32 MMA accumulators retain
the original admitted bounds; their reconstructed dots and intervals fit signed int64.

## Ties and failure flags

A tile survives when its encoded maximum upper bound is **greater than or equal to** the largest
encoded lower bound over all tiles. Thus the actual largest score, every tied score and the smallest
token index among those ties survive. The existing `decode_greedy_select` publishes tokens, `seen`
and results with its original tie rule.

Any tile containing a nonfinite interval endpoint also survives. This check happens before reducing
tile maxima, including negative endpoints in nonwinning columns. At common scale `s`, RNE overflows
exactly at integer magnitude `(2**128 - 2**103)/2**s`. For `s >= 66` the kernel constructs this exact
integer threshold; for `s < 66` the entire admitted int64 domain is finite. A marker at `2**62`,
outside the possible interval range, carries the nonfinite condition through the integer maximum.

The interval encoder never sets the error flag. Every surviving tile is recomputed with the full
nine digit-pair integer MMAs, original encoder, FTZ and nonfinite reporting. The one activation is
replicated across the tensor instruction's sixteen rows; only its first output row is consumed.
Non-surviving tiles have finite bounding endpoints, so they contain no overflowing full score.
Consequently the full and bounded paths produce the same token, selector state and failure flag.

## Request ownership and storage

Compressed weights are rebuilt after the request's live weight exponents, including in-place ES
changes and restore. No compressed weight values survive request exit. The retained buffer pointer
is reused when the original weight object and binding are unchanged, so captured graphs stay valid.
Rebinding invalidates the captured session through the existing graph signature and the helper also
checks its weight binding. Single-row, uncached and penalty requests do not build the compressed copy.

Admission includes the retained `V*K` bytes and conservative temporary interval/summary/winner
storage before allocation. `buffers()` includes the compressed copy for boundary clearing checks.
The private `session.last_logits` diagnostic is `None` for bounded decode; use the unchanged forward
APIs when full logits are required.

## Verification scope

Tests compare full and bounded token IDs, flags, `seen`, results and graph reuse. They include
duplicate/all-equal rows, signed zero, FTZ, tails, row tiles, maximum K, nonfinite activations, live
weight changes/restore, exact RNE overflow neighbors, outward rounding and workspace admission.
The interval premise is checked against the independent CPU integer reference. PTX/SASS are
audited for SM80/86/89/90/120; the existing integer runtime requires SM80 or newer.

Trained model parity, cross-host comparison, native Windows and end-to-end timings must be read
from the dated evidence receipts. Operator timings and passing fixture tests alone establish none
of those broader claims.
