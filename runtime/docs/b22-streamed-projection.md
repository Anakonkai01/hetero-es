# Streamed integer projections (`mma_schedule="stream"`)

An execution schedule for the row-scaled integer contract of [integer-projection-v1.md](integer-projection-v1.md).
Activation and weight quantization, the exact integer dot, reconstruction, final encoding, bias add and error
flags are unchanged; only the order in which exact integer terms are added and the data movement differ.

## Execution

`integer_stream` runs every eligible MMA projection: reduction width K divisible by 16, packed activation planes
and live FP16 weights 16-byte aligned. Other shapes and layouts keep the tile kernel (`integer_linear`); the
single-row SIMT path is unchanged.

- A CTA (four warps) owns 64 output columns and one 16- or 32-row tile; each warp owns 16 columns (two n8 MMA
  tiles). Raw FP16 weight rows and the packed activation digit planes stream through three shared-memory stages
  of 64 K values with 16-byte `cp.async` copies (zero-filled beyond the matrix, the K tail and the row count).
  Weights are quantized from shared memory, once per CTA; there is no persistent or global transformed weight.
- Split-K divides the 64-wide K stages into contiguous ranges, one per `blockIdx.z` (a range may be empty).
  Partials are the same exact int64 sums combined by the existing `integer_finish`. The decode plan is unchanged.
- Inside each 32-wide MMA step, thread t holds physical K values 8t..8t+7 for both operands (fragment slots
  4t..4t+3 and 16+4t..16+4t+3). Both operands use the same permutation of K, so every product pairs the same
  activation and weight; an exact integer sum does not depend on the order of its terms, and each int32 degree
  accumulator keeps the bound of integer-projection-v1.md (at most three digit dots of K terms).
- Shared-memory rows are XOR-swizzled (weights by row parity, activations by bit 1 of the row) so 16- and
  8-byte fragment reads are conflict-free. Every shared buffer is 16-byte aligned.

## B22 digit conversion

`quant_half` widens FP16 exactly, adds s<<23 to the FP32 bits with s=21-E (E is the row exponent, in [-24,15], so
s is in [6,45]) and converts with `cvt.rni`. The streamed kernel performs the same exponent addition, then adds
1.5*2^23 with `add.rn.f32`: for |g|<2^22 the sum lies in [2^23,2^24), where the FP32 unit in the last place is 1,
so the add rounds g to the nearest integer with ties to even exactly as `cvt.rni`, and the result bits are
0x4B400000+q. Adding 0x8080-0x400000 yields q+0x8080 above 0x4B000000, whose three low bytes are the balanced
radix-256 digits (d0 and d1 with their top bit flipped, d2 as is); byte permutes pack four elements per digit word.

Zero and non-finite halves need no branch. A signed zero becomes a normal float below 2^-80. An Inf/NaN
(exponent field 255) wraps modulo 2^32 to exponent field s-1 with some sign, also below 2^-80. Both round to
q=0, which is what `quant_half` returns for them; non-finite weights are still rejected by the row-metadata pass.
An opt-in test compares the two conversions for all 65,536 half patterns and all 40 row exponents (every quad that
can occur in a row with that exponent). B14 keeps `quant_half`, because its shift can be negative.

## Measured scope

Receipts are in [`2026-10-26-strict-projection-shapes`](../../docs/evidence/2026-10-26-strict-projection-shapes/README.md).
They do not establish universal hardware qualification, model quality, or the managed execution path.
