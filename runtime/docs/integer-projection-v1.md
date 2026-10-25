# Experimental row-scaled integer projection

This is a separate arithmetic reference, `row_scaled_signed_integer_dot_v1_experimental`, permitted for feasibility
work by [ADR-012](adr/ADR-012-single-model-strict-inference.md). It is not the historical adjacent-pair FP32 tree.
The graph adapter composes it with the existing strict FP32 nonlinearities and canonical RoPE constants. No managed
recipe, default, qualification or historical noise/perturb/update/restore contract changes.

## Reference operation

Inputs are finite FP32 activations and finite FP16 weights/bias. The admitted reduction width is 1 through 32768.
Magnitude precision B is exactly 14 or 22 and is part of the portable identity.

1. Flush FP32 activation subnormals to signed zero and widen FP16 weights exactly. For each activation row and each
   weight output row independently, choose E=floor(log2(max(abs(row)))); an all-zero row uses E=0. Integer bit ordering
   determines this maximum. Neither batching nor a tile/split-K choice may change E.
2. Quantize each value by exact ties-to-even integer rounding: q=RNE(value / 2^(E-(B-1))). The inclusive bound is
   abs(q)<=2^B. There is no float reciprocal or float intermediate scale. NaN/Inf fail even if their quantized value
   would otherwise disappear from the dot product.
3. Compute S=sum(qx[k]*qw[k]) exactly, then encode the exact value S*2^(Ex+Ew-2*(B-1)) to IEEE FP32 with one RNE
   rounding. Flush a rounded subnormal to signed zero. An integer zero sum publishes positive zero by definition.
4. Add optional FP16 bias using the existing separate FP32 RNE add and integer FTZ. Any nonfinite result fails before
   token publication; there is no ordinary floating GEMM fallback.

The encoder constructs the FP32 sign/exponent/significand with integer operations. For an underflowing normal
exponent, it rounds in units of 2^-149 before FTZ: the midpoint immediately below minimum normal rounds *up* to
minimum normal. Multiplying by a precomputed FP32 scale would lose this boundary. Overflow, carry and negative
underflow have explicit tests. Rational test oracles use `Fraction` and a search over representable FP32 values,
avoiding an intermediate binary64 rounding.

## Exact integer execution

Balanced radix-256 signed digits reconstruct q exactly. Low digits are in [-128,127], the final digit in [-64,64].
B14 uses two digits and four MMA products; B22 uses three digits and nine products. Equal radix degrees share three
or five int32 accumulator groups rather than four or nine independent groups.

- Every individual digit dot is bounded in absolute value by K*128^2 <= 2^29. A degree groups at most three dots,
  so every intermediate signed sum is bounded by 3*2^29 < 2^31, regardless of reduction order.
- Reconstructing the degree groups in int64 is safe even with the looser bound of 128 for *all* three digits:
  K * (128*(1+256+65536))^2 = 2^29*65793^2 < 2^62. This bounds the sum of absolute terms and every reconstruction
  partial sum. The tighter final result bound is K*2^(2B) <= 2^59. Signed multiplication by positive powers of two
  avoids a signed-left-shift assumption.
- Split-K partitions the same entire K into disjoint 32-wide stripes with one global scale per row. Bounded int64
  partials are combined exactly in a separate kernel, with no float atomic/reassociation. The default workspace
  cap is 16 MiB and is checked before quantization. SIMT and MMA implement the same arithmetic.

The CUDA prototype uses `mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32`. The fragment assignment follows the
[NVIDIA PTX integer m16n8k32 layout](https://docs.nvidia.com/cuda/parallel-thread-execution/index.html#warp-level-matrix-fragment-mma-16832).
The nonoverflow proof above is required; merely selecting integer Tensor Cores is insufficient. Generated PTX and
SASS must contain the signed integer MMA/IMMA and pass the strict operator audit. Float multiplication/FMA/MUFU
instructions in an integer module are refused. One rejected runtime split stride caused compiler-generated float
reciprocal control code; the selected split stride is a compile-time constant. Native Windows remains untested.

## Weights, request lifetime and memory

Original live FP16 weights are read and quantized inside each tile. There is no full FP32 or fully quantized second
weight matrix. Activations have bounded per-projection quantized intermediates. Weight row exponents cost four bytes
per output row; the graph admission budget adds these retained metadata bytes explicitly.

Standalone operator calls rescan live weights on every call. The graph adapter refreshes all projection exponents
at the beginning of **every** generation request, while holding its generation lock, and checks the error flag before
prefill/capture/replay. Exponents are constant only within that locked request. In-place perturbation or restore,
including an exponent-changing update, therefore refreshes the same stable buffers before graph reuse. Request exit
clears the metadata and synchronizes before releasing the lock, including noncached and failure paths.

Metadata bindings use weak references plus pointer/shape/stride/dtype/device checks; stable pointers never imply
unchanged contents. Rebinding parameters, stream or capacity first discards the old capture. Calls outside generation
do not use retained request metadata. Concurrent weight writes by an external actor are unsupported, as for the
existing strict decoder; the prototype is not a replacement for managed GPU ownership.

## Evidence and remaining gates

Receipts: [integer feasibility](../../docs/evidence/2026-10-25-strict-integer/RESULTS-01.md). CPU rational answers, physical
GPU encoder boundaries, odd widths/tails, precision identity, compiler audit, batch/permutation equality, live-weight
changes and graph composition are distinct checks. Synthetic matrix speed is not trained-model throughput.

Before promotion, finish multi-model parent/canonical-candidate measurements, cross-GPU token/reward equality,
perturbation sensitivity and numerical/quality assessment, exact restore/failure/resource ownership, source/native
packaging and the remaining M0–M6 system gates. All identities retain `hardwareQualified:false`. Comparing a new
integer reference with itself establishes implementation equality, not equivalence to the FP32 tree or model quality.
