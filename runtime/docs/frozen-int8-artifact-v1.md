# Frozen int8 base artifact v1 (experimental)

Status: implemented CPU oracle for the M6 feasibility experiment. It is not an accepted backend, not a managed
recipe, and not a claim about model quality or speed. `heteroes/eval/frozen_int8.py` is the reference for this
identity; no CUDA operator or graph integration exists under it yet.

## Scope

One linear weight matrix `W` with logical shape `[N, K]`, stored as signed int8 rows plus one FP32 scale per output
row, used with the existing B22 activation reference and, later, FP16 LoRA adapters. The base weights are immutable.
There is no dequantized FP16 weight tensor in the runtime representation.

## Weight quantization

For each output row `n` independently:

1. Read the source row as exact FP32 values (FP16 input is widened exactly). Reject nonfinite values. FP32
   subnormals are read as their exact binary values, not flushed.
2. Let `A = max_k |W[n,k]|` as an exact rational of the binary input values. If `A = 0`, store scale `+0.0` and
   `q[n,k] = 0` for every `k`.
3. Otherwise let `s = ceil_fp32(A / 127)`: the least positive finite FP32 value greater than or equal to the exact
   rational `A / 127`. The scale is always positive, and `A / s <= 127`.
4. Store `q[n,k] = RNE(W[n,k] / s)`, where `s` is the exact value of the stored FP32 scale and RNE is
   round-to-nearest with ties to even. Because `A / s <= 127`, `q` lies in `[-127, 127]`; `-128` is never emitted and
   there is no clipping step. A nonzero row whose exact maximum is below `127 * 2^-149` is rejected rather than
   given a scale that cannot reach the admitted integer range.
5. The stored scale is the FP32 bit pattern produced by `ceil_fp32`, not a value re-rounded by a float division.

The quantizer computes the row maximum exactly and the ceiling by exact rational comparisons. Quantization then uses
a binary64 quotient followed by ties-even `torch.round`; this is exact by the following bound. Write `q = m/D` with
integer `m` and `D`, where `D <= 2^25` for a quotient in `[0.5, 127]` (from `q <= 127` and the 24-bit source
significand). A non-tie exact quotient is at least `1/(2D) >= 2^-26` from a half-integer, while binary64 division
error near the admitted range is below `2^-46`. An exact tie is representable in binary64, so the correctly rounded
division returns it exactly and `torch.round` applies ties-even. A program assertion rejects any escaped integer
instead of clipping.

The scale rule is deliberately not the engines' `absmax / 127` followed by clipping. Directed rounding up keeps the
full `[-127, 127]` range available without a saturation branch, at a relative scale cost of at most one FP32 ulp.
A different rule is a different artifact identity.

## Activation and projection

The activation contract is the existing B22 row quantizer in `heteroes.eval.integer_reference.quantize_rows`
(`magnitude_bits=22`): per-row power-of-two exponent, exact integer RNE, FP32 subnormals flushed to signed zero,
all-zero rows use exponent zero, and `|q| <= 2^22` including the endpoints. The projection does not replace this with
a vendor `absmax/127` scale.

For each output element:

```
S = sum_k qx[m,k] * qw[n,k]                    (exact integer dot, int64)
T = S * signif(scale[n])                       (exact integer product)
e = exponent_of_scale[n] + ex[m] - 21          (21 = 22 - 1)
y = encode_fp32_rne(T * 2^e)                   (one final RNE, then signed-zero FTZ)
```

`signif` and `exponent_of_scale` are decoded from the stored FP32 scale: a normal scale is `signif * 2^(E-150)` with
`signif` in `[2^23, 2^24)`, and a subnormal scale is `signif * 2^-149`. The exact dot bound is
`|S| < 127 * 2^22 * K < 2^44` for the admitted `K <= 32768`, so int64 accumulation is exact. `|T| < 2^68`, which does
not fit int64; the reference uses Python integers and a future CUDA operator must use a two-limb (96-bit) product and
a single exact RNE/FTZ encoding. Multiplying an int64 dot by an FP32 scale and calling the result exact is forbidden
under this identity.

The encoder accepts an exact integer `T` with `|T| < 2^96` and an exponent not below `-2048`; values above the
largest finite FP32 are rejected, not rounded to infinity. It rounds subnormals in units of `2^-149`, then flushes
signed zero. A value that rounds up to the smallest normal survives. The CPU result is independent of the output
tile, row order, batch size and host FPU.

Bias, when present, is the existing FP16 bias and is added through `heteroes.eval.reference_ops.add` after the
projection, exactly as the current integer reference does. The result is FP32; later graph operators own the normal
FP16 publication.

## Packed layout

- `weight_q`: contiguous `int8`, shape `[N, K]`, output-major. Row `n` occupies `K` consecutive bytes in increasing
  `k`. This is the column-major B operand for a `K x N` GEMM and matches the per-output-row scale.
- `weight_scale`: contiguous little-endian `float32`, shape `[N]`.
- No padding is stored in the artifact. A kernel may pad `K` to its MMA width and `N`/`M` to its tile, but padding
  is not part of the logical artifact and must contribute exact zeros.
- Artifact files are little-endian. Reading on a big-endian host is unsupported and fails explicitly.

## Container and identity

The artifact is one file:

```
offset  size            content
0       8               magic "HESFINT8"
8       8               header length L, unsigned little-endian u64
16      L               canonical UTF-8 JSON header (sorted keys, no whitespace)
16+L    N*K             weight_q bytes, row-major
...     N*4             weight_scale bytes, little-endian float32
```

For format version 1 the header has exactly these keys:

```
activationLimbs 3
format          "heteroes.frozen-int8-b22"
formatVersion   1
magnitudeBits   22
maxWidth        32768
metadata        caller JSON object (for example parent files, model id/revision, creation note)
operator        "frozen_int8_b22_exact_reference_v1_experimental"
quantizer       "per_output_channel_int8_ceil_absmax_over_127_rne_v1_experimental"
shape           [N, K]
tensors         {"weight_q": {dtype: "int8", shape: [N, K], sha256},
                 "weight_scale": {dtype: "float32", shape: [N], sha256}}
weightLayout    "output-major-k-contiguous"
weightRange     [-127, 127]
```

The file SHA-256 is returned by the writer; the reader may require it. The tensor hashes cover the exact payload
bytes, so a header-only edit or a payload-only edit fails before use. The header cannot contain its own file hash;
the expected hash is recorded by the caller (evidence, recipe or test). The writer validates the structural
invariants (dtypes, shapes, range, zero-row/zero-scale relation); it does not re-quantize or prove that a caller's
`q`/`scale` came from the claimed source weights. Provenance belongs in `metadata` and in the pinned file hash.

## Failure modes

The reader and quantizer fail explicitly on: nonfinite weight or scale, shape mismatch, `K > 32768`, `N < 1` or
`K < 1`, `q = -128`, a nonzero weight row with zero scale, a zero weight row with nonzero scale, a negative or
negative-zero scale, NaN or infinite scale, a truncated or oversized file, trailing bytes, bad magic, malformed or
noncanonical JSON, duplicate header keys, an unknown or non-integer header identity field, a tensor descriptor with
the wrong dtype/shape/hash, a tensor hash mismatch, or an artifact hash mismatch when one is supplied.

## Verification

`runtime/tests/eval/test_frozen_int8.py` contains the independent Fraction/bit-search oracle, exact ceiling and RNE
boundaries, encoder overflow and subnormal boundaries, artifact determinism and tamper tests, and projection tests
against the rational oracle with bias, row permutation and output tiles. The committed mutation run kills 16 of 16
mutants.

## What this does not establish

No CUDA implementation, graph integration, LoRA training, model-quality result, throughput measurement, cross-GPU
token equality or managed acceptance. The CPU path is an oracle and may be slow by design. The format is
experimental and may be replaced by a new versioned identity; existing artifacts must not be reinterpreted under a
new rule.
