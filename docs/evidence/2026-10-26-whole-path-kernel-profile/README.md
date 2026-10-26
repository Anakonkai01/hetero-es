# Whole-path kernel profile of strict B22 and the vendor-FP16 control

Claude session, 2026-10-26, after auditing checkpoint `e6053385`. Selected runtime source is still B22
`b1ef257a` (`git diff b1ef257a e6053385 -- runtime/src` is empty). Local RTX 5070 Ti, Torch 2.13.0+cu132,
pinned Qwen2.5-0.5B from the read-only strict model folder, batch 32, context capacity 512, greedy.

Unlike `2026-10-26-strict-remaining`, no timing nodes are inserted into the captured graph. Each case runs
one warmup generation, checks token equality, times one plain generation, then traces one whole generation
with the PyTorch/CUPTI profiler and checks its tokens again. `summarize.py` groups kernel time into categories;
all numbers below come from `summary.log` and `attention-slope-01.log`.

| Case | token/s (plain) | GPU span ms | Projection GEMM | Attention | Projection prep/finish | Norm/act/RoPE/add | Copies | GPU idle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B22 short32 | 4362.6 | 258.6 | 58.5% | 14.0% | 8.1% | 5.0% | 0.6% | 30.6 ms |
| B22 chat128 | 3899.7 | 1090.4 | 52.8% | 27.9% | 7.1% | 4.7% | 0.2% | 63.9 ms |
| FP16 short32 | 7530.0 | 149.7 | 35.2% | 24.2% | — | 8.6% | 10.7% | 25.4 ms |
| FP16 chat128 | 6107.3 | 710.9 | 29.1% | 42.9% | — | 7.3% | 9.0% | 63.3 ms |

Per-step strict attention for B22 chat128 (prompts 57–142 tokens, left padded):

| Step | Attention ms/step | µs per layer |
| --- | ---: | ---: |
| 0 (prefill) | 43.089 | 1795.4 |
| 1 | 1.426 | 59.4 |
| 64 | 2.043 | 85.1 |
| 127 | 2.757 | 114.9 |

Findings used for the next step:

- Decode attention grows almost linearly with the cache length, about 0.4 µs per key per layer for
  32 rows × 14 heads × dim 64. That is roughly 32 KB of FP32 K/V per key-layer, so the kernel moves on the
  order of 80 GB/s, far below the card's memory bandwidth. The source explains the shape: one block per
  (query, head), so each GQA K/V row is read by seven blocks; a thread reads a whole 256-byte key row; and
  the value product runs one thread per channel serially over all keys.
- With vendor FP16 projections, attention is already the largest cost on chat128 (42.9%). Faster projections
  alone (B13 or otherwise) cannot approach vLLM on longer generations while this attention remains.
- B22 projection kernels remain the largest B22 cost (52.8–58.5%), plus 7–8% input/finish kernels.

## What this does NOT show

A speedup of any kind; no runtime code changed. One traced generation per case on one GPU and one model,
with CUPTI tracing overhead not separately measured; no SM86, native Windows, vLLM or other-model profile.
The category split is by kernel name; "GPU idle" is span minus the union of kernel intervals and includes
host work and launch gaps. It does not explain why the earlier warp-attention prototype gained only ~1% in
whole generation; that remains to be checked against this per-step data. No push, merge or deployment.
