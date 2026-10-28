# Exact reciprocal lookup feasibility

The target is the existing five-step reciprocal sequence, including its rounding quirks. This is not a
correctly-rounded mathematical reciprocal or a replacement algorithm for the numerical contract.

Write each admitted positive FP32 input as `x = a * 2^e`, with `a` in `[1,2)` and its 23-bit mantissa `m`.
Subtracting the FP32 input encoding from the fixed seed `0x7EF311C3` changes the seed exponent by `-e`
and leaves its significand identical to the normalized-input seed. In each iteration, `x*r` is invariant
under these opposite power-of-two scalings. So is the separately rounded subtraction `2 - x*r`. The
final multiplication scales `r` by exactly `2^-e`. All intermediates remain finite and normal throughout
the admitted `[1e-30,1e30]` domain: seeds/results have reciprocal size, products/corrections stay near one.
FP32 round-to-nearest commutes with exact power-of-two scaling in this range. Induction therefore gives
the exact same normalized mantissa result after every one of the five original steps.

Build the 2^23-entry normalized table using the original separate FP32 operations. The lookup result is
that table's FP32 encoding minus `e * 0x800000`. CPU `exhaust.py` checks all **1,671,934,059** admitted positive
FP32 encodings against the original five-step NumPy sequence, and sampled independent Torch reference
tests cover every exponent field and the domain boundaries. The table SHA-256 is
`c30d9363d614f4ac77143bc2e5e5f63c5ee14056e3b7d4eafd96e2c62ef4253a`.

The 32 MiB table is losslessly compressed. Store one exact anchor per 2048 mantissas and the endpoint at
the next power of two, predict each encoding with an integer chord, and store the exact residual in a
nibble. Every residual is checked to fit `[-8,7]` during construction; all 2^23 reconstructed entries are
checked against the original table. In this table the observed residual range is `[-2,3]`. The packed
payload plus anchors is **4,210,692 bytes**. Prediction is only an integer storage codec: its error never
reaches arithmetic results, because the stored residual reconstructs every table value exactly.

The GPU probe passes explicit table pointers, so it adds no hidden global pointer or candidate state.
Outside the declared positive domain it executes the original reciprocal function, preserving the original
domain/nonfinite flags and NaN behavior. SiLU's exponential and surrounding rounded multiplications are
unchanged. PTX/SASS audit enforcement remains enabled.

## What this does NOT show

The CPU exhaustive check is not GPU or decoder qualification, and exactness does not establish speed.
GPU tests and warm-table operator controls are separate gates; cold-cache/full-model performance,
resource admission, lifecycle/failure behavior, other hardware, Windows and packaging remain required
before any implementation is selected. No current runtime source/default is changed by this experiment.
