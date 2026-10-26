# Streamed B22 projections, grouped launches, fused input quantization, queued decode (IN PROGRESS)

Claude session 2026-10-26 (afternoon). Folder not sealed yet: no SHA256SUMS, cross-host runs pending.

Commits: `878018e3` (integer_stream + one queued decode step), next commit (grouped QKV / gate+up launch,
fused RMSNorm/SiLU quantization). Arithmetic contract unchanged (exact integer sums; tokens equal).

Qwen B32, 5070 Ti, single-process ABAB (`harness/bench_single.py`), tokens identical in every run:

| Source | short32 tok/s | chat128 tok/s |
| --- | ---: | ---: |
| `75f92c30` (B22 tile + GQA) | ~4745 | ~4878 |
| `878018e3` (stream + queued step) | ~6975 | ~7100 |
| + grouped launches | ~7421 | ~7581 |
| + fused RMSNorm/SiLU quantization (working tree) | ~7609 | ~7791 |

Smol/Tiny at `878018e3`: 5195→6517, 2474→4050 short32. Raw: `raw/single-*`, later runs in
`.scratch/claude-projection-20261026/bench/` (not yet copied here).

Done locally: `tests/eval/test_integer_stream.py` (stream vs CPU oracle/tile for all splits, exhaustive fast
digit conversion, grouped launch, fused ops), `test_strict_decode_pipeline.py`; strict GPU suites 971 passed at
`878018e3`; mutation 11/13 stream (2 equivalent: non-finite mask redundant → removed; K-tail weight guard is
memory-safety only), 7/7 pipeline; trained Qwen/Smol/Tiny parent/±/restore tile==stream and equal to the sealed
GQA receipts; real-EOS Qwen chat (27/32 rows end) captured == uncaptured.

Rejected (measured, kept in scratch): persistent stream-K, in-kernel semaphore split reduction, cluster/DSMEM
split reduction, 4B cp.async ring for attention (all slower).

## What this does NOT show

3060 WSL2 / native Windows parity and timing, check-all/packaging, mutation of grouped/fused code, quality or
learning, near-vLLM performance (~55% of the 13835 control), managed activation. No push/merge/deploy.
