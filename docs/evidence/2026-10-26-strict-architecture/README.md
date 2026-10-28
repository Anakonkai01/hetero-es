# Whole-path controls and rejected architecture pilots

Base selected runtime `b1ef257a`, recorded under HEAD `4d488217`. These are unselected scratch
experiments, sharing one primary trained Qwen FP16 model. No runtime source was changed.

The projection control replaces all strict projections, including the head, with vendor FP16 GEMM.
Separate and merged projection variants retain the own graph's other strict operators. This changes
arithmetic and is a diagnostic control, not a solution to heterogeneous strict inference. Warmup and
capture are excluded. Each variant has ten interleaved host-wall samples; output length is fixed,
EOS is disabled, and every run must reproduce its own warmup token IDs.

| Qwen, batch 32 | Selected B22 token/s | Separate FP16 | Merged FP16 |
| --- | ---: | ---: | ---: |
| Eight-prompt pool, 32 outputs | 4,349 | 7,492 | 7,804 |
| First 32 recorded GSM8K chat prompts, 128 outputs | 3,960 | 6,073 | 6,243 |

This control motivates work beyond projections: vendor projections alone still leave a substantial
gap to the earlier short-workload vLLM control. It does not quantify independent costs of all other
operators. Instrumented wall regions include GPU waiting; `read` time must not be labeled CPU cost.
`projection-controls-5070ti-01.json` records regions, raw samples, model/workload identities and tokens.

A shared-radix B22/B14 GEMM pilot stages packed activation tiles once per CTA, stages/quantizes live
raw FP16 weight tiles, and uses ldmatrix with different warp layouts. Four parameterized GPU oracle
tests pass, including tails, offsets and split partitions. Five operator cases, thirty calls per
graph replay, give baseline/prototype ratios 0.828–1.114 for N32/K32 and 0.652–0.979 for N64/K64.
There is insufficient consistent gain: stop this branch before full-model qualification.

A separate one-shape captured-prefill pilot preserves selected B22 operations and reuses persistent
input/layout buffers. Two tiny Qwen/Llama-layout GPU tests match the independent CPU decoder through
changed inputs, live weights and restore, and verify request-buffer clearing. The trained benchmark
checks exact token equality with B22, capture reuse and final clearing. The following ten-sample
results reject the hypothesis that eager prefill submission is a material bottleneck here:

| Qwen, batch 32 | Selected B22 token/s | Captured B22 | Captured vendor FP16 |
| --- | ---: | ---: | ---: |
| Short32 | 4,365.4 | 4,364.4 | 7,866.8 |
| Chat128 | 3,953.1 | 3,955.7 | 6,254.8 |

Short prefill wall time is 60.718 ms eager versus 60.599 ms captured; chat prefill is 210.769 ms
versus 210.242 ms. Those differences do not establish a useful throughput gain. Peak GPU allocated
memory across the three graph wrappers sharing one primary model is 2.750 GiB. Context capacity is
1024 for the first control and 512 for the capture pilot, recorded in each harness. Do not treat
comparisons across these separate pilots as controlled same-run differences.

Final harness sources and the investigation notes are retained in `harness/`. Use
`PYTHONPATH=runtime/src:<this-folder>/harness` and the isolated environment with explicit GPU opt-in.
The scripts refer to local read-only model/cache paths and the sealed chat workload. Initial red
tests remain beside final green receipts. Next work should examine remaining GPU work and fusion
on the whole inference path before committing to another small operator rewrite.

## What this does NOT show

A selected speedup, independent exclusive GPU timings from wall-region instrumentation, native or
cross-GPU acceptance of the prototypes, complete stream/concurrency/resource qualification, arbitrary
model support, quality or learning acceptance, or near-vLLM speed. No push, merge or deployment occurred.
