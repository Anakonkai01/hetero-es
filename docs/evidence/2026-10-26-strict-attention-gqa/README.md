# Distributed strict attention with GQA tile sharing

Claude session, 2026-10-26. Base: selected runtime B22 `b1ef257a` (checkpoint `f64453d4`). The earlier
[whole-path profile](../2026-10-26-whole-path-kernel-profile/README.md) showed strict attention at 27.9% of
B22 Qwen chat128 time, growing about 0.4 µs per key per layer, far below memory bandwidth.

## What changed

`runtime/src/heteroes/eval/strict_cuda.py` gains two kernels and a launcher; arithmetic is unchanged.

- `strict_attention_split`: one block per (query, head) as before, but scores use dim/8-lane shuffles and the
  value reduction is split into aligned power-of-two key chunks merged by the same counter.
- `strict_attention_gqa` (default when eligible): one block per (query, KV head) for all query heads sharing it.
  Each K/V element is loaded, flushed and checked once per block (instead of once per head) in 32-row tiles with
  16-byte prefetch; scores use dim/32 lanes of 4 aligned groups; values push aligned 32-key tile roots.
- Eligibility: power-of-two head dim >= 32, 2..512/dim query heads per KV head, shared memory <= 48 KiB.
  Otherwise the split kernel runs. `_attention_entry = "strict_attention"` keeps the original as a control.

Why it is exact: `strict_attention` reduces with a binary counter over 8-wide groups. That equals the pruned
aligned in-place tree with the left operand first, and that tree splits exactly at aligned power-of-two chunks
(levels below the chunk size stay in a chunk; higher levels are the same pruned tree over chunk roots). The
maximum is order-independent except for a zero's sign, which both normalize to +0. Every product, add, flag
check and masked-key load still runs exactly once per head; loads that are now shared only OR flags.

## Results (numbers from `summarize.py` → `summary.log`)

Whole generation, batch 32, ABBA five rounds, tokens equal in every sample:

| Host | Model / case | Original token/s | Selected token/s | Gain |
| --- | --- | ---: | ---: | ---: |
| 5070 Ti Linux | Qwen short32 | 4360.6 | 4776.3 | +9.5% |
| 5070 Ti Linux | Qwen chat128 | 3952.6 | 4905.7 | +24.1% |
| 5070 Ti Linux | Smol short32 | 4509.9 | 5204.0 | +15.4% |
| 5070 Ti Linux | Tiny short32 | 2322.4 | 2471.0 | +6.4% |
| 3060 WSL2 | Qwen short32 | 1347.8 | 1394.7 | +3.5% |
| 3060 WSL2 | Qwen chat128 | 1263.6 | 1386.7 | +9.7% |
| 3060 WSL2 | Smol short32 | 1519.5 | 1623.0 | +6.8% |
| 3060 WSL2 | Tiny short32 | 634.9 | 662.0 | +4.3% |

Kernel-only CUPTI durations on the 5070 Ti, Qwen shape (14/2 heads, dim 64, 32 rows), `raw/attention-kernels-5070ti-01.log`:
decode at 143/270/512 keys 62.8/114.6/208.4 µs → 18.3/31.2/54.0 µs (3.4–3.9×); prefill 32×142 4.61 → 2.34 ms.
After the change, `profile/summary-02.log` puts B22 chat128 attention at 11.5% and projections at 64.9% (+8.8%
input/finish kernels): projections are now the dominant cost.

Correctness:

- `tests/eval/test_strict_attention_split.py`: 287 tests (GPU-gated except chunk/eligibility rules) compare both new kernels with the original for bits
  and failure flags (dims 1..256 incl. odd, 1..4096 keys, -0, subnormal keys/values, cancellation, equal scores,
  NaN/Inf, masked overflow, packed ragged spans) and with the independent CPU oracle; one test compiles the ops
  source for sm_75/80/86/89/90/120 and runs the PTX/SASS instruction audit.
- Local strict GPU suites on the final source: 979 passed (`checks/gpu-strict-suites-5070ti-01.log`). `checks/`: full check-all ALL PASS, runtime CPU 3223 passed/683
  skipped, backend 452; Linux package check passes and the Worker runtime archive carries the new kernel source
  (`checks/package-kernel-source.json`).
- 3060 WSL2: 565 strict tests passed. Native Windows 11 / 3060 (isolated venv): 581 passed.
- Trained Qwen/Smol/Tiny, parent, canonical seed 7001 ±σ and restored parent (Qwen also 32 chat prompts × 128
  tokens): prefill logits and tokens are identical original vs selected on every host, identical across 5070 Ti
  Linux, 3060 WSL2 and (Qwen) 3060 native Windows, and equal to the sealed `b1ef257a` receipts on both GPUs.
- Mutation (`mutation/`): 14/16 kernel/launcher mutants killed. Two are equivalent: removing one staged-load
  `note` (every staged element enters a product, whose `mul_` notes a nonfinite) and dropping the split kernel's
  lane pruning (it only adds +0, which can change only the sign of an all-zero score, and that cannot change
  exp, the maximum after +0 normalization, outputs or flags). Of four `#pragma unroll 1` guards, the two that
  current NVRTC needs are killed by the multi-architecture audit test; the other two are harmless guards.

Failure retained: the first 3060 run (`raw/3060-wsl2-01-audit-failure/`) failed the instruction audit. On
sm_86 NVRTC computed an unrolled runtime-stride loop's trip count with MUFU.RCP integer division (sm_120 was
clean). The fix keeps those loops rolled; `raw/cubin-equal-01.log` shows the source run remotely (pragma
indentation only differs) compiles to identical PTX/cubin on sm_86 and sm_120. `raw/bench-qwen-01-INVALID-*`
is a harness defect (a class attribute made both engines use the new kernel); `bench-qwen-02.json` is its fix.

## What this does NOT show

Near-vLLM performance (Qwen B32 is still about a third of the earlier vLLM control), a projection speedup, broad
model/GPU coverage beyond these three checkpoints, 5070 Ti and 3060, timed native Windows throughput, managed
lifecycle/ownership activation, quality or learning, or universal hardware qualification. Finite tests and
receipts support, but do not replace, the exactness argument above. No push, merge, deployment or lab change.
