# Balanced B22 degree-accumulator instruction order, 2026-10-27

Unselected SM120 scheduling experiment against `0eb86cb9`. Visit all nine digit pairs in degree order
`2,1,3,2,0,1,2,3,4` instead of row-major digit order. The three degree-two updates are three products
apart, with the same five bounded int32 accumulators. The exact integer degree bounds admit every
partial addition in either order; no product, rounding or bias changes. No extra accumulator is added.

`raw/tests-01.log`: **6 passing** CPU-oracle groups, each checking two column tiles and three splits,
bias/no bias, empty partitions and tails. `raw/mutation-01.log`: control passes and the wrong-radix-degree
mutant is killed. Instruction audits remain unchanged.

`raw/operators-01.json`, matched graph controls, warm medians in microseconds:

| M / K / N / split | Original | Reordered | Original repeat |
| --- | ---: | ---: | ---: |
| 888 / 896 / 4864 / 1 | 240.20 | 240.22 | 241.24 |
| 888 / 4864 / 896 / 1 | 243.54 | 245.64 | 244.69 |
| 32 / 896 / 9728 / 2 | 23.89 | 23.81 | 23.92 |
| 32 / 4864 / 896 / 7 | 12.90 | 13.14 | 12.89 |
| 32 / 896 / 1152 / 5 | 6.00 | 6.16 | 6.15 |
| 32 / 896 / 896 / 7 | 5.20 | 5.38 | 5.19 |

Registers/shared memory/residency remain the same. Explicitly cold timings also show no material gain.
**Keep the original order.** No whole-generation promotion or additional parameter search follows this
inconclusive/slower screening. The measurements do not establish the exact compiler scheduling reason.

## What this does NOT show

No faster selected decoder, 80% result, full edge/failure qualification, trained cross-host/native parity,
package acceptance or learning effect is established. No deployment, lab-state or environment changes occurred.
