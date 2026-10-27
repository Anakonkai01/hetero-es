# Fuse exact QKV finish with GQA attention, 2026-10-27

Unselected SM120/B22 probe against runtime `0eb86cb9`. The original grouped QKV projection still
produces the same integer split partials. A single CTA owning one (row, KV head) then finishes Q/K/V,
applies the original RoPE operations, stores its K/V slot and runs the original ordered attention tree.
Query remains shared instead of round-tripping through a global tensor. A uniform CTA barrier precedes
all K/V prefetches; different owners have disjoint cache regions. The caller supplies physical
`max_keys=state.context`, which must not be inferred from the active row count after EOS compaction.

`raw/tests-01.log`: **15 passing** operator cases comparing valid output bits, complete KV cache bits
and flags against original QKV-store then attention. Covers rows 2/17/32, bias/no bias, zero, invalid
weight/cache and overflow cases. This run preceded the host API correction requiring explicit
`max_keys`; GPU kernel source did not change. The final 15-case module was not rerun afterward.
`raw/graph-tests-01.log`: **1 passing** final-API graph test with a Qwen-shaped one-layer fixture,
parent/change/restore token and last-logit-bit comparison, stable capture and shrinking EOS owners.
The initial import failures are retained separately.

Final-source Qwen B32 full synchronized-request pilot, five samples after warmup, original short32/chat128
workloads, prefix reuse and EOS stopping off:

| Case | Token/s |
| --- | ---: |
| short32 | 9864.80 |
| chat128 | 9862.00 |

Token hashes match the selected control (`bc4a5504e37c…`, `a9fad5ca48ed…`); all report harness hashes
match final files. The actual fused `qkv-attention-v1-s5-b1` build is retained in the report.
Against selected results near 9866/9890 this screen shows **no whole-request improvement**.
**Park the fusion.** Fewer launches alone are not evidence of useful speedup. This is a pilot screen,
not a paired proof of exact performance equality or regression size.

## What this does NOT show

No faster selected runtime, final complete operator-suite pass, mutation acceptance, trained canonical
candidate/cross-host/native qualification, package/resource acceptance, learning effect or 80% result
is established. Runtime source, lab state and deployment remain unchanged.
