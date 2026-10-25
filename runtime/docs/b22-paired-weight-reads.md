# B22 paired weight reads

This execution change preserves the row-scaled integer arithmetic. It reads two adjacent live FP16
weight bit patterns with one 32-bit global load before applying the existing `quant_half` and
`pack_digits` separately to each half. It creates no persistent quantized or FP32 weight copy.
MMA products, integer reconstruction, rounding, bias addition, overflow checks and split-K bounds
are unchanged. The single-row SIMT decode kernel is unchanged.

The load is valid only when the base pointer is four-byte aligned, the row width is even and both
elements are in bounds. Each tile starts at a multiple of 32 elements; each pair offset is even.
Consequently the row and pair address are also four-byte aligned. CUDA's little-endian layout puts
element `k` in bits 0–15 and `k+1` in bits 16–31. Odd widths, two-byte-offset storage and partial
tails use guarded scalar loads. Missing elements are positive zero, as in the scalar implementation.
No new arithmetic operation is performed on the weight values themselves.

`weight_load="scalar"` retains the previous reads. `"paired"` forces this guarded implementation
for numerical comparisons. `"auto"` selects paired reads only for B22 on SM120; other architectures
and B14 retain scalar reads. This is a measured execution policy, not a general hardware claim:
the SM86 prototype regressed on TinyLlama. Kernel identities record requested/effective policies
and distinct compiled build names. Decoder configuration checks reject changing the policy after
construction, including within an active graph session.

Tests compare both load modes with the independent CPU arithmetic for B14/B22, even and odd widths,
partial tiles, aligned and offset storage, bias, signed zero, FP32 subnormals and extreme finite FP16
weights. Real-model timing and canonical candidate/restore receipts are scoped separately in
[`2026-10-25-b22-core-perf`](../../docs/evidence/2026-10-25-b22-core-perf/README.md).
These checks do not enable managed strict execution or establish general model/hardware qualification.
