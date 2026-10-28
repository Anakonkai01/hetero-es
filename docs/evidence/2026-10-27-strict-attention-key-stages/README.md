# Larger ordered GQA K/V stages, 2026-10-27

Unselected SM120 research against runtime `0eb86cb9`. Retain the Qwen 448-thread CTA, load 64 or 128
keys per shared-memory stage, and consume the original ordered 32-key score/value subtrees inside it.
No identity padding, reassociation, FTZ or precision change is introduced. This reduces stage barriers
while preserving each checked FP32 operation. Unsupported shapes use the original path.

`raw/tests-01.log`: **60 passing** operator cases for both stage sizes, keys 1/33/65/129/257/511 and
normal/zero/tiny/nonfinite/overflow scenarios. Valid output bits and failure flags match the original.
Afterward the host helper was changed to remember the configured opt-in shared-memory limit, avoiding
redundant `cuFuncSetAttribute` calls during capture; GPU source was unchanged. `raw/graph-test-02.log`
adds **1 passing** capture/replay test with changed live queries and the 128-key opt-in shared stage.
These are two runs, not a claim that the final 61-test module was run together. Initial failure is retained.

Matched graph-replayed operator medians in microseconds, synthetic tensor values with actual short-prompt
lengths and physical context bound 512:

| Batch / decode step | Original | Stage 64 | Stage 128 |
| --- | ---: | ---: | ---: |
| 32 / 1 | 12.040 | 12.056 | 11.796 |
| 32 / 16 | 14.344 | 13.852 | 13.608 |
| 32 / 31 | 15.124 | 14.640 | 14.380 |
| 32 / 80 | 21.028 | 20.260 | 20.764 |

At this bound, original/stage64/stage128 shared bytes are 38968/47416/64312 and registers 82/78/106.
All admit one 448-thread CTA per SM. Full samples, repeated original controls and smaller-batch cases
are in `raw/operators-01.json`; its source hash matches the final helper.

**Keep as an unselected candidate.** Roughly 3–5% savings at some attention steps is not a whole-decoder
gain. No full-generation pilot or combination with request-sized caches was run.

## What this does NOT show

No full-request speedup, final combined-suite pass, mutation acceptance, trained parent/canonical
candidate/restore qualification, cross-host/native or packaging acceptance, learning effect or 80%
result is established. The selected runtime and lab state remain unchanged.
