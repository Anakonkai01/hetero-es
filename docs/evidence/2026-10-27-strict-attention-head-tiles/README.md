# GQA repeat-head CTA tiling, 2026-10-27

Unselected research against runtime `0eb86cb9`, measured on the local RTX 5070 Ti / SM120.
Split a KV owner's seven query heads into two- or four-head CTAs. Live heads retain the original
checked FP32 trees. Inactive lanes still stage K/V and reach every barrier, but omit value arithmetic
and output stores so dummy heads cannot introduce failure flags.

`raw/tests-01.log`: **50 passing** operator cases. They compare valid output bits and failure flags
against the original GQA kernel, with partial head groups, dimensions 32/64/128, key tails,
zeros/tiny values, nonfinite inputs and overflowing intermediates. The initial import failure is retained.

Matched graph-replayed operator medians in microseconds, with actual short-prompt length distribution,
synthetic tensor values and the original physical context bound of 512:

| Batch / decode step | Original | Two heads/CTA | Four heads/CTA |
| --- | ---: | ---: | ---: |
| 32 / 1 | 12.120 | 12.132 | 12.584 |
| 32 / 16 | 14.456 | 14.368 | 15.128 |
| 32 / 31 | 15.104 | 15.516 | 15.904 |
| 32 / 80 | 21.008 | 21.624 | 22.112 |
| 8 / 16 | 14.344 | 11.536 | 12.612 |
| 2 / 16 | 8.228 | 6.680 | 7.232 |

Original/tile2/tile4 theoretical resident warps are 14/20/24; local frames remain 72 bytes.
Higher theoretical occupancy does not help the B32 target. The repeated original controls are in
`raw/operators-01.json`. **Reject for the B32 goal.** Smaller-batch improvements do not replace that goal.

## What this does NOT show

No whole-request gain, mutation qualification, trained parent/candidate/restore or native/cross-host
acceptance, package/resource acceptance, learning effect or 80% result is established. Runtime source
and lab state remain unchanged. This is a rejected operator screen, not a selected implementation.
