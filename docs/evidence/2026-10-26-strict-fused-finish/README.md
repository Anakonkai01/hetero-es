# Fused decode finishes, split greedy, prefill host stalls, 32-column decode CTAs

Claude session 2026-10-26 (evening). Base `d4030b52` (sealed in `../2026-10-26-strict-projection-shapes/`).
Commits: `5cc72926` (fused finishes + shuffle-tree RMS quantization), `96e2a0db` (GPU-size independent split-K
tests), `fd7418a2` (split greedy), `ac3c6f4c` (prefill host stalls, prefill RMSNorm fused with quantization),
`e3293fb1` (parallel prefix cache copy), `1c9a54b9` (32-column decode CTAs, test gaps closed). Arithmetic
contract unchanged: every output, token and failure flag equals the unfused kernel sequence.

## What changed

- `finish_qkv_rope`: the split Q/K/V partials are encoded and immediately put through strict_rope (q and k) and
  decode_store (k and v). `finish_silu` + `pack_rows`: strict_silu_mul of each encoded gate/up pair, the row maximum
  (order-independent) and the packed digit planes. `finish_residual`: strict_add(hidden, projection).
- `strict_rms_quant` reproduces block_tree's pruned aligned tree with register, warp-shuffle and warp-leader levels.
- Greedy selection over 8192-column chunks, then an in-order combination (largest score, smallest index on a tie).
- Generation: the prefill status is checked after the cache copy and first selection are queued; prompt masks are
  validated with one host read; the prefill slabs are copied without per-sequence view checks; integer prefill fuses
  the norms feeding Q/K/V and gate/up with quantization; the prefix copy is strided over 16 CTAs.
- Decode plans stream projections through 32-column CTAs (8 columns per warp); prefill keeps 64 columns.

## Results (numbers from `summarize.py` → `summary.log`)

Whole generation, batch 32, separate processes ABAB from one manifest-checked stage (base `d4030b52`, new
`1c9a54b9`), tokens identical in every run and equal on both GPUs:

| Host | Model / case | d4030b52 token/s | 1c9a54b9 token/s | Gain |
| --- | --- | ---: | ---: | ---: |
| 5070 Ti Linux | Qwen short32 | 7490.5 | 8579.8 | +14.5% |
| 5070 Ti Linux | Qwen chat128 | 7476.5 | 8722.2 | +16.7% |
| 5070 Ti Linux | Smol short32 | 7085.7 | 8103.8 | +14.4% |
| 5070 Ti Linux | Tiny short32 | 4205.9 | 4461.6 | +6.1% |
| 3060 WSL2 | Qwen short32 | 2569.9 | 2657.8 | +3.4% |
| 3060 WSL2 | Qwen chat128 | 2527.2 | 2620.8 | +3.7% |
| 3060 WSL2 | Smol short32 | 2474.3 | 2782.8 | +12.5% |
| 3060 WSL2 | Tiny short32 | 1352.8 | 1381.0 | +2.1% |

The final 5070 Ti pairs ran while the CPU-heavy packaging check was running, so both columns are a few percent
below an idle host (the earlier idle measurement of `d4030b52` was 7590/7775); the ratio is ABAB-paired. The
intermediate `5cc72926` receipts (`raw/*-01-5cc72926/`) measured +6.2%/+6.5% Qwen on an idle 5070 Ti.
The vLLM control (13835 token/s Qwen short32) is still about 1.6× faster.

## Correctness

- New tests: `tests/eval/test_integer_fused_finish.py` (each fused finish against the unfused kernels for several
  widths/heads, with and without bias, failures, a nonfinite bias, ineligible shapes; a hidden-256 Qwen-like decoder
  with distinct norms against the CPU oracle and the unfused graph), split greedy against the single-CTA kernel
  (ties across chunks, ±0, NaN, no selectable score), prompt-mask validation, both stream column widths against the
  CPU oracle and the tile kernel, extended fused RMS widths.
- 5070 Ti GPU suites on the final source: integer/decode/adapter suites passed (348 + 42 + 166 + 161 in the runs
  of this session); runtime CPU `tests/eval` 680 passed / 715 skipped. 3060 WSL2: 914 strict/integer/FP16-adapter
  GPU tests passed (`raw/3060-wsl2-02/tests-3060-02.log`; the first run's four failures were the GPU-size dependent
  split-K assumption fixed in `96e2a0db`).
- Trained Qwen/Smol/Tiny parent, canonical seed 7001 ±σ and restored parent (Qwen also chat 32×128 and a real-EOS
  run, 27/32 rows ending early, captured = uncaptured): tile = stream on each host, both hosts equal, and equal to
  the sealed GQA receipts (`../2026-10-26-strict-attention-gqa/`).
- Mutation (`mutation/`): 23/28 on `5cc72926`; the two real gaps (a nonfinite bias only the finish sees; odd head
  dims) got tests in `1c9a54b9` and are killed in the rerun (2/2). The other three are equivalent: swapping the
  operands of an IEEE add (commutative) in two tree levels, and atomics from every even lane instead of one per warp
  (the same maximum).
- Packaging: `scripts/build-apps.sh --check` at `1c9a54b9` passed (`checks/build-apps-check-receipt.json`); the Worker
  runtime archive carries the changed runtime sources byte for byte (`checks/package-kernel-source.json`).

## What this does NOT show

Native Windows for these commits (the base is covered in the sealed folder), near-vLLM performance, quality or
learning, broad model or GPU coverage beyond three checkpoints on a 5070 Ti and a 3060, managed lifecycle or
activation, or universal hardware qualification. No push, merge, deployment or lab change.
