# Prefill M64/N32 with warps split over M, 2026-10-27

Unselected SM120 research against `0eb86cb9`. A 256-thread CTA has two four-warp groups owning distinct
32-row slices, sharing a 64-row activation tile and 32-column weight tile. Each thread retains the same
two m16 fragments and five integer degree accumulators as the 32-column stream kernel. Producer strides,
consumer rows, output rows and grid-Y all change together; integer products, encoding and bias do not.
This is different from merely increasing the warp count of the old tile.

`raw/tests-02.log`: **5 passing** CPU-oracle groups, each checking splits 1/3/7, including empty partitions,
row/column/K tails, bias, extreme FP16 and signed zero. `raw/mutation-01.log`: control passes and **2/2
mutants killed** (missing warp-M output offset, wrong input half). The first helper attempt failed a
source replacement assertion and is retained separately. Existing PTX/SASS audits remain unchanged.

`raw/operators-01.json`: matched graph timings, with warm and explicitly L2-evicted cases. All variants
equal the original FP32 bits. Warm medians, microseconds (M888):

| K / N | Original M32/N64 | M64: two stages, two CTAs | M64: two stages, three CTAs | M64: three stages, two CTAs |
| --- | ---: | ---: | ---: | ---: |
| 896 / 4864 | 239.98 | 264.19 | 263.94 | 264.24 |
| 4864 / 896 | 243.54 | 268.64 | 269.88 | 262.51 |
| 896 / 1152 | 65.78 | 71.18 | 70.48 | 70.15 |
| 896 / 896 | 50.96 | 54.30 | 54.89 | 53.36 |

The three-CTA variant uses **80 registers, 48 local bytes, 32768 shared bytes**, allowing 24 resident
warps. Two-CTA variants use **118/116 registers, no local bytes** and 16 resident warps. Cold controls
also regress. More theoretical occupancy does not produce a faster kernel here; no specific causal
attribution to spills or shared operand traffic is established by these timings.

**Reject the tile.** Do not spend full-model/native acceptance work on a consistently slower operator.

## What this does NOT show

No faster selected decoder, whole-generation improvement, 80% result, full invalid-input/failure
qualification, trained candidate cross-host/native parity, package acceptance or learning effect is
established. The selected runtime remains unchanged. No lab state, deployment or environment changed.
