# Request-sized physical KV context, 2026-10-27

Unselected graph-lifecycle research against runtime `0eb86cb9`, on the local RTX 5070 Ti. After original
input validation, round maximum actual prompt length plus generation budget up to 16 physical KV slots,
bounded by configured `max_context`. Public context limits, graph identity validation and conservative
memory admission remain based on the original configured limit. A context change releases the old
session; same-context requests reuse it. Decode addressing and attention bounds use the physical session
context. Every request still clears its live caches; this is not prefix caching or prompt deduplication.

`raw/tests-02.log`: **2 passing** cases. A tiny Llama fixture compares tokens and last-decode FP32 logit
bits with the independent CPU B22 reference across in-place weight change/restore and physical contexts
16 -> 32 -> 16, checks cleared caches and same-bucket capture reuse, and checks original context/budget
rejections. The first run failed a test-only CPU logit indexing assertion; its receipt is retained and
not counted as a pass. Concurrent use is refused before the new request-context field can change.

Original Qwen B32 full synchronized-request pilot, five samples after warmup, configured context 512,
prefix reuse and EOS stopping off:

| Case | Token/s | Physical context | Physical KV bytes |
| --- | ---: | ---: | ---: |
| short32 | 9951.29 | 128 | 100663296 |
| chat128 | 9903.44 | 272 | 213909504 |

The original configured-512 cache has 402653184 bytes. Token hashes match selected controls
(`bc4a5504e37c…`, `a9fad5ca48ed…`); report hashes match the final harness. The short pilot is about
0.86% above the previously measured selected control, **not a fresh paired ABAB result**. No combination
with TMA or larger attention stages was measured.

**Keep as an unselected candidate.** Before promotion, extend lifecycle tests to EOS compaction,
stream/capacity changes, parameter replacement, refusal/failure cleanup and concurrent requests; run
mutants, matched ABAB and trained canonical candidate/restore qualification.

## What this does NOT show

No universal graph-lifecycle proof, full failure/mutation acceptance, selected speedup, trained
cross-host/native parity, package/resource qualification, learning effect or 80% result is established.
The selected runtime, configured admission policy, lab state and deployment remain unchanged.
