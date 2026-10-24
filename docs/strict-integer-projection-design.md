# Next performance experiment — NOT IMPLEMENTED OR ACCEPTED

Current selected source preserves the FP32 tree. Its B32 projections still lag vLLM by ~18–28x on three trained
models. ADR-012 explicitly permits a separately versioned fixed-point numerical reference. Do not alter v1 arithmetic
or recipe/noise/ES/ledger semantics under their old identity. No managed activation until all gates pass.

Candidate: row-scaled signed-integer dot products on integer Tensor Cores, with magnitudeBits B=14 first (two signed
8-bit limbs, four integer MMA products); B=22 may be a higher-precision comparison (three limbs, nine MMAs).
This is a DIFFERENT arithmetic contract, not an implementation of the adjacent-pair FP32 tree. Accuracy/sensitivity
and actual speed are hypotheses requiring receipts. Do not promise close-to-vLLM performance from hardware peaks.

Proposed independent reference:

1. Normalize FP32 activation subnormals to signed zero; widen FP16 weights exactly. Reject every nonfinite input/bias.
2. For EACH input row and EACH output-weight row independently, find E=floor(log2(max_abs)) by integer bit ordering;
   all-zero rows use E=0. Scales never depend on another row, batching, tile shape, prefix slicing or GPU architecture.
3. Quantize with exact integer round-to-nearest/even: q=RNE(value / 2^(E-(B-1))). Then |q|<=2^B, including that
   positive endpoint. For FP32 normal bits, q is significand24 right-shifted by Emax-Evalue+24-B with integer ties-even.
   Zero/subnormal is handled explicitly; clamp shift counts before executing to avoid undefined shifts.
4. Integer dot S=sum(qx[k]*qw[k]) across the entire admitted K<=32768. Define one final exact scale
   e=Ex+Ew-2*(B-1); convert the exact integer S*2^e to IEEE FP32 RNE, then flush a rounded subnormal to signed zero.
   S=0 publishes +0 by definition. Nonfinite output fails. Add FP16 bias with the existing separate RNE+integer FTZ.
5. Implement scaled-integer->FP32 by integer sign/exponent/significand construction, NOT a float scale that can
   underflow before multiplication. For final E<-126, round to units of 2^-149 first: only an upward round to the
   smallest normal survives FTZ. Preserve sign of underflowed nonzero S. Handle exponent carry and overflow explicitly.
6. All other graph operators/nonlinearities remain the existing reference, explicitly composed in the new identity.

Tensor Core decomposition:

- Balanced signed radix-256 digits: d0=int8(q & 255), rem=(q-d0)>>8, d1=int8(rem & 255), and (for B22)
  d2=(rem-d1)>>8. B14 high digit stays within [-64,64]; B22 top digit does too. This avoids unsupported unsigned
  dot variants. Test both signs, carry/borrow boundaries and endpoints independently.
- Every signed int8 limb dot has |partial|<=128^2*32768=2^29, safely inside int32. Integer MMA accumulation is exact
  without overflow, so unspecified floating Tensor Core accumulation order is irrelevant. Use only integer MMA;
  audit generated PTX/SASS and inspect register/spill/shared resources on SM86/SM120.
- Reconstruct S in int64 as sum(dot(di,dj)*2^(8*(i+j))). Prove absolute partial-sum bounds <2^63. Avoid C++ signed
  left-shift UB; use defined integer operations/unsigned shifts with a proven bounded signed reconstruction.
- Triton int8 tl.dot is a possible prototype, after inspecting installed/official primary source APIs. Tiled FP16
  weights are converted on the fly; NEVER retain a full FP32 or fully quantized second weight matrix/model on GPU.
- Weight-row exponents are small metadata, refreshed from LIVE FP16 weights at EVERY candidate/request before use,
  including in-place ES perturb/restore; stable pointers do not establish unchanged contents. Activation exponents
  are per-row per-projection. Capture may reuse buffers but must not reuse stale exponent values.

Gates before adoption:

- Meaningful CPU tests FIRST: independent scalar integer RNE/encoding oracle, endpoint/carry/subnormal/overflow,
  signed zeros, cancellation and odd K. CPU integer matmul only when int64 nonoverflow is proved.
- Independent CUDA operator answers on both architectures for non-model widths 768/1024/2048/4096 and boundaries;
  larger K, output tails, batch/permutation/chunk consistency, nonfinite failures, no hidden full weight copy.
- Capture/compile/resource identities and scratch mutations. Preserve failures/slower prototypes.
- Raw operator speed must justify full decoder integration. Then compare three trained models vs current strict/HF,
  parent AND canonical perturbed candidates, quality/logits/token behavior, perturbation sensitivity, exact restore,
  fresh-cache semantics and cross-GPU token/reward equality. Finite comparisons supplement the operation proof.
- New backend/reference version with magnitudeBits/scaling/rounding/reconstruction and nonlinear/source identity.
  No ordinary vendor fallback, no hardware qualification from a passing model hash, no managed recipe change.

The full M0–M6 plan remains open, including watchdog/D10, recovery/retention, GPU role ownership, native Windows,
SDK/API/UI qualification, system acceptance and one quantized frozen-base/LoRA format. Do not redefine completion.
