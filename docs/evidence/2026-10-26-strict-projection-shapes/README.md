# Streamed B22 projections, grouped launches, fused input quantization, queued decode

Claude sessions 2026-10-26 (afternoon and evening). Commits: `878018e3` (integer_stream + one queued decode
step), `22511cdf` (grouped QKV / gate+up launch, fused RMSNorm/SiLU quantization), `96bec7d1` (multi-architecture
audit of the fused source), `d4030b52` (tests that close mutation gaps, below). Arithmetic contract unchanged:
exact integer sums, same encoding and flags; tokens and logits equal the earlier selected kernels.

## What changed

- `integer_stream` (`runtime/docs/b22-streamed-projection.md`): 64-column CTAs, three cp.async stages of raw FP16
  weights and packed activation planes, exact byte-digit conversion, the same K permutation on both MMA operands.
- The captured decode loop replays step t+1 before reading step t; a failure in a step queued before an EOS is undone
  and recomputed for the survivors, so outputs and failures equal the unqueued loop.
- One streamed launch (and one finish) for Q/K/V and for gate+up; `strict_rms_quant` / `strict_silu_quant` compute
  the strict row in shared memory and emit the packed planes `quantize_input` would produce.

## Results (numbers from `summarize.py` → `summary.json`)

Whole generation, batch 32, separate processes ABAB from one manifest-checked stage archive (base `75f92c30`
vs new), median of medians; tokens identical in every run, and the token hashes are the same on both GPUs:

| Host | Model / case | 75f92c30 token/s | New token/s | Gain |
| --- | --- | ---: | ---: | ---: |
| 5070 Ti Linux | Qwen short32 | 4761.0 | 7589.2 | +59.4% |
| 5070 Ti Linux | Qwen chat128 | 4902.5 | 7775.0 | +58.6% |
| 5070 Ti Linux | Smol short32 | 5190.1 | 7312.5 | +40.9% |
| 5070 Ti Linux | Tiny short32 | 2472.1 | 4302.1 | +74.0% |
| 3060 WSL2 | Qwen short32 | 1398.6 | 2550.5 | +82.4% |
| 3060 WSL2 | Qwen chat128 | 1400.1 | 2509.2 | +79.2% |
| 3060 WSL2 | Smol short32 | 1657.8 | 2476.2 | +49.4% |
| 3060 WSL2 | Tiny short32 | 665.2 | 1353.9 | +103.5% |
| 3060 native Win11 | Qwen short32 | 1369.9 | 2523.0 | +84.2% |
| 3060 native Win11 | Qwen chat128 | 1395.6 | 2523.0 | +80.8% |

Same-session 5070 Ti steps (Qwen; `raw/single-*-0[12]`, `raw/progression/`): 75f92c30 → 878018e3 about
4745 → 6972 short32; grouped launches 6976 → 7422; fused quantization 6984 → 7609 (each against 878018e3).

The earlier vLLM control (13835 token/s Qwen short32, same workload) is still about 1.8× faster.

## Correctness

- Tests: `tests/eval/test_integer_stream.py` (stream vs CPU oracle and tile kernel for every split, exhaustive fast
  digit conversion, grouped launches incl. split-K groups of three matrices, fused RMSNorm/SiLU planes and flags,
  PTX/SASS audit of the integer and fused sources for sm_75..sm_120), `test_strict_decode_pipeline.py`,
  `test_integer_decoder.py` (incl. a hidden-256 decoder with distinct norm weights against the CPU oracle and the
  grouped workspace bound).
- 5070 Ti: GPU `tests/eval` 1329 passed / 10 skipped at `22511cdf` (`checks/gpu-eval-5070ti-02.log`); full
  `scripts/check-all.sh` ALL PASS at `96bec7d1` (`checks/all-01/`: runtime CPU 3224 passed / 761 skipped,
  backend 452). 3060 WSL2: 858 strict/integer GPU tests passed (`raw/3060-wsl2-01/tests-3060-01.log`).
- Native Windows 11 / 3060 (isolated venv, manifest-checked archive of `96bec7d1`): 706 tests passed, trained Qwen
  parity and the first timed native throughput (`raw/3060-native-01/`).
- Trained Qwen/Smol/Tiny, parent, canonical seed 7001 ±σ and restored parent (Qwen also 32 chat prompts × 128
  tokens and a real-EOS run, 27/32 rows ending early, captured = uncaptured): tile and stream engines agree on every
  host, all hosts agree, and the results equal the sealed GQA receipts (`../2026-10-26-strict-attention-gqa/`).
- Mutation (`mutation/`): stream kernel 11/13 (two documented in the interim notes: a redundant nonfinite mask,
  since removed, and the K-tail weight guard, memory safety only); queued loop 7/7. Grouped/fused code: 12/23 in
  the first run. Five survivors were real test gaps (no split-K group of three matrices, no finish-only nonfinite
  flag, fixtures with all-ones norms, an unchecked grouped workspace bound); `d4030b52` adds those tests and
  the rerun of the 11 survivors (`mutation-group-fused-02.log`) kills those five. The other six are documented:
  admitting single-row groups is unreachable (single rows are quantized unpacked and are never stream-eligible);
  the quantizer's subnormal and nonfinite checks are redundant for these rows (every value comes from `mul_`,
  which already flushes and flags); the packed-tail guard and the two missing barriers are memory-safety and race
  guards that a finite run cannot observe reliably (the RMS barrier no longer exists after `5cc72926`).

## What this does NOT show

Near-vLLM performance, quality or learning, broad model or GPU coverage beyond these three checkpoints on a 5070 Ti
and a 3060, managed lifecycle or activation, or universal hardware qualification. Finite tests and receipts
support, but do not replace, the exactness arguments in `runtime/docs/b22-streamed-projection.md`. The packaging
check for these sources is recorded with the next change (`../2026-10-26-strict-fused-finish/`), which builds on
them. No push, merge, deployment or lab change.
