# Unselected fast B14 weight conversion

The original streamed B14 route uses scalar `quant_half`/digit packing. This prototype generalizes B22's
exact bit-based conversion to B14, explicitly mapping zero/Inf/NaN halves to zero before exponent-bit
adjustment (B14 scales can be negative), and writes the third byte plane only for B22. The B22 source
extraction marker is generalized in v2. Reproducible patch against `267ba0b5` is in `harness/fast14-v2.diff`.
The original source and production defaults are unchanged.

An initial compilation rejects B14 under the old B22-only guard (`red-01.log`). The parameterized exhaustive
converter test then passes **2 tests**, covering every FP16 bit pattern and every admitted row exponent
for **both B14 and B22** (`exhaustive-01.log`). It compares every packed byte with original quantization,
including zeros and nonfinites. The full modified test source is retained under `harness/`.

The parent Qwen B32 curve improves old B14 short32 from about **9662 to 10067 token/s**, still only **72.8%**
of the matched vLLM control. See [whole-path controls](../2026-10-27-whole-path-controls/README.md) for exact
settings and [the finite output survey](../2026-10-27-strict-precision-quality/README.md) for 640 rows per
precision matching original B14 on 3060 WSL2. That survey also finds reward changes relative to B22.

## What this does NOT show

This is not a B22-equivalent decoder, a selected default, full operator/native/mutation acceptance, broad
quality acceptance or an 80% goal result. The prototype is parked after its speed/quality controls; no ES
update, learning claim, deployment or lab state change was made.
