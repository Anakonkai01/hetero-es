# Head coarse-bit hierarchy density, 2026-10-27

Offline screening against `0eb86cb9`, using the trained parent Qwen checkpoint on the local 5070 Ti.
The existing head uses one signed byte: shift 15 gives **eight signed bits** (seven magnitude bits plus
sign). Four signed bits require shift 19. This distinction matters when comparing older shorthand.

The CPU test (`raw/bounds-tests-01.log`) checks the exact floor composition and integer interval. The
GPU study (`raw/density-01.json`) captures a copy of the final decode hidden state, rebuilds fresh
request metadata, and evaluates shifts 15–19. FP64 GEMM serves only as an **exact integer** dot evaluator:
integer operands/products and all intermediate sums stay below `2^53`. It is not proposed as a runtime
kernel. Integer center/radius, outward common-exponent rounding and RNE bounds follow the existing head.
For shift 15, **every tile upper/lower bound matches the selected kernel bit for bit**.

## Results and decision

Each case contains 32 rows; there are 4748 vocabulary tiles per row. The selected winning tile is kept
for **all 160 rows at every tested bit width**. Median / maximum surviving tiles:

| Last decode checkpoint | Signed 8 bits | Signed 7 bits | Signed 6 bits | Signed 4 bits |
| --- | ---: | ---: | ---: | ---: |
| short2 | 1 / 21 | 3 / 180 | 74 / 3421 | 4748 / 4748 |
| short8 | 1 / 7 | 2 / 33 | 74 / 575 | 4748 / 4748 |
| short32 | 1 / 2 | 1 / 4 | 10 / 102 | 4748 / 4748 |
| chat32 | 1 / 5 | 2 / 17 | 19 / 285 | 4748 / 4748 |
| chat128 | 1 / 3 | 1 / 8 | 4 / 789 | 4748 / 4748 |

**Do not write the proposed native-int4 → byte refinement pipeline from this evidence.** Its first
stage keeps essentially the entire vocabulary; it would add work before almost the same byte scan.
Five signed bits are also very loose (medians 3069–4667 tiles). Seven-bit packing remains only an
unmeasured idea with a smaller bandwidth opportunity and unpacking cost; native int4 speed cannot be
ascribed to it. No new head kernel is selected or implemented.

## What this does NOT show

No head or decoder speedup, 80% result, universally small candidate set, arbitrary-model bound
qualification, candidate/restore parity, cross-host/native acceptance, overflow/NaN edge qualification or
learning effect is established. The 160 rows are specific parent inference checkpoints. The original
byte-head runtime, flags and request ownership remain unchanged. No deployment or lab state was changed.
