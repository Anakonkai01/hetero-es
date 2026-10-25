# Source selection before final acceptance

Select prepacked activation planes alone. The baseline preserves the raw public quantization default and SIMT
single-row path, quantizes/encodes MMA input once per call, and shares the same planes across each fanout. No tensor
survives a call or captured request beyond the existing bounded graph lifetime. Width tails are explicitly zero.

The packed tensor is DIGITS*rows*ceil(K/4)*4 bytes. Relative to the conservative FP32 input term, positive excess
only occurs at very narrow K; admission now adds that exact positive difference for every projection occurrence,
capacity and maximum context before request metadata/cache allocation. Red/green narrow graph tests exercise this.

Do not select the additional shift or integer-conversion variants. After prepacking, shift B32 differences are
below1%, with B8 regressions; the direct-integer weight fast path loses across models despite passing all admitted
FP16/exponent pairs. Correct arithmetic alone does not justify promotion of slower code. Raw receipts are retained.

The segmented grouped launch from the adjacent folder remains unselected: modest gains, additional routing code.
Revisit after profiling the new kernel; it must preserve packed inputs if combined. Its earlier baseline-source
receipts must not be represented as tests of this new source.

## What this does NOT show

Prototype timings are not final selected-source trained/candidate/native/managed acceptance. The active full
M0–M6 scope and the near-vLLM target remain open. No defaults/recipe activation, push, merge, deploy or learning.
