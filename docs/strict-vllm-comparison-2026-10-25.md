# HeteroES versus vLLM — measured 2026-10-25

Selected HeteroES source `3fd704a5` reaches 23–27% of the prior measured vLLM default B32 throughput on three
models. B8 is 95–119% of the surveyed vLLM batch-invariant result; B1 exceeds that mode but is about half of default.
The near-vLLM objective is not met. Full M0–M6 remains active; managed strict/default remains inactive.

## Same-workload local 5070 Ti measurements

Total output tokens/s; B32 aggregates all 32 sequences. FP16 weight storage, greedy, 32 output tokens, context 512,
EOS stopping and prefix reuse disabled. Eight prompts form the pool: B1 uses the first, B8 each once, B32 repeats
four times. One warmup is excluded; median of three synchronized host wall measurements includes prefill/decode
and host overhead. Separate environments/builds, unisolated GPU and sequential measurement stages apply.

| Model          | Batch | HeteroES selected B22 | vLLM default | vLLM batch-invariant | Default / selected |
| -------------- | ----: | --------------------: | -----------: | -------------------: | -----------------: |
| SmolLM2-360M   |     1 |                 277.3 |        529.2 |                173.8 |              1.91x |
| SmolLM2-360M   |     8 |                1493.9 |       4093.2 |               1371.2 |              2.74x |
| SmolLM2-360M   |    32 |                3861.3 |      14429.4 |               5339.8 |              3.74x |
| TinyLlama-1.1B |     1 |                 187.5 |        322.9 |                103.2 |              1.72x |
| TinyLlama-1.1B |     8 |                 783.9 |       2330.6 |                825.3 |              2.97x |
| TinyLlama-1.1B |    32 |                1804.6 |       7791.8 |               3194.7 |              4.32x |
| Qwen2.5-0.5B   |     1 |                 277.5 |        518.7 |                146.0 |              1.87x |
| Qwen2.5-0.5B   |     8 |                1386.4 |       4037.9 |               1164.5 |              2.91x |
| Qwen2.5-0.5B   |    32 |                3470.5 |      13802.5 |               4697.2 |              3.98x |

The selected execution includes exact weight conversion, shared quantization, bounded decode split-K, prepacked
activation planes and exact grouped attention trees (`3fd704a5`). The latest step groups 8 products into aligned
canonical subtrees without adding zero nodes or changing rounding. ABBA same-process controls on three models
show B32 gains 7.5–13.7% on 5070 Ti and 6.2–11.7% on 3060. Actual selected-source benchmarks are the table above.
[Exact source/cross-GPU comparison](evidence/2026-10-25-attention-tree/selected-trained-comparison-01.json),
[tree argument](../runtime/docs/attention-tree-execution.md). The integer arithmetic remains a separate reference
from the historical FP32 pairwise tree; no precision was reduced in this optimization.

## Direct source comparison, not a language explanation

The locally inspected vLLM source is pinned at `e7473bf6862289f0647d1f4b01498288b181e063`; the measured installation
is vLLM 0.32.0. Source observations describe that pin, not every backend/version or the exact dispatch of every op.

| Mechanism                 | Inspected vLLM source                                                                                                    | HeteroES selected source                                                                                             | Consequence / next action                                                                                                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Linear dispatch           | Python `UnquantizedLinearMethod.apply` dispatches to a backend; default unquantized path is `torch.nn.functional.linear` | Python launches NVRTC CUDA C++/PTX integer kernels                                                                   | Both delegate GPU math to compiled kernels. Rewriting the outer Python in C++ does not remove the arithmetic/layout gap.                                                                 |
| Q/K/V and MLP projections | Llama uses `QKVParallelLinear` and `MergedColumnParallelLinear` for gate/up                                              | `linear_many` quantizes input once, then launches independent `_linear` calls                                        | Segmented grouping was tested under 97f62431: B32 gains 1.5–5.6% locally, so it remains unselected. Preserve prepacked inputs if revisited.                                              |
| Arithmetic work           | Native floating GEMM; batch-invariant path uses floating `tl.dot`                                                        | B22 uses three balanced int8 limbs and nine limb products per dot tile, plus conversion/packing/int64 reconstruction | Exact portability has a real cost. MMA shapes differ, so nine limb products is not a claim of exactly nine times hardware work or runtime. Keep the separate identity and measure costs. |
| Fusion                    | Merged gate/up feeds `SiluAndMul`; RMSNorm supports fused residual add                                                   | SiLU/multiply is already fused; residual add and RMSNorm are separate calls                                          | Inspect add+norm fusion next, preserving the specified FP32 rounding tree. Do not claim every fusion is absent.                                                                          |
| Execution and KV          | CUDA graph modes, optimized attention and paged KV allocation                                                            | Captured decode exists, fixed-owner bounded full-context KV                                                          | Graph existence alone is not the gap. Paging primarily helps allocation/concurrency; current short fixed-batch timings do not establish that as the main bottleneck.                     |

Specific inspected files: [Llama merged projections](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/models/llama.py#L95),
[linear dispatch](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/layers/linear.py#L232),
[default GEMM](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/layers/utils.py#L83),
[batch-invariant dot](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/determinism/batch_invariant.py#L119),
[CUDA graph design](https://docs.vllm.ai/en/latest/design/cuda_graphs/).
Local counterparts are `runtime/src/heteroes/eval/integer_cuda.py:linear_many/_linear` and
`strict_decoder_graph.py:_decode_core`. Prefix caching is off in the comparison, so prefix hits do not explain it.
Current-source trained profiles put 66–84% of B32 CUDA event time in projections and 10–20% in attention.
These event sums include prefill/decode and profiling overhead; they are not wall-time shares. The next targets
are projection memory/packing work and exact attention reduction execution. Decode already uses the true prefix
length; max_context is not a count of keys unnecessarily computed by each decode query.

## Latest experiments, not selected

- Four-product SIMT scheduling improves 5070 Ti B1 by 3.6–11.3%, but regresses 3060 B1 by 1.0–3.0% across
  the same three models. Aligned 64-bit MMA weight reads improve 5070 Ti B32 by 1.1–6.4%, but regress
  TinyLlama on 3060 by about 4% at B8/B32. Both remain unselected; no model-name-specific exception was added.
  Same-process ABBA controls retain exact parent tokens/final logits across both GPUs, with complete file manifests
  and passing compiled PTX/SASS audits. These finite checks do not establish candidate/native/managed acceptance.
  [SIMT decision](evidence/2026-10-25-simt-vector/DECISION-01.md),
  [MMA decision](evidence/2026-10-25-mma-vector/DECISION-01.md).
- Uniform one/two-warp groups regress geometric mean on both 5070 Ti and 3060 across 40 shape/batch cases. Retain 4 warps.
- Row tiles 64/128 under the preceding raw-activation packing regress overall on both devices. On 5070 Ti tile 64 uses 237–241 registers/thread; tile 128 spills
  336–424 bytes/thread. Increasing tile size alone is not sufficient.
- Under preceding 97f62431, shift/PRMT prototypes improved trained B32 by 6–9%. After prepacking, shift gains
  are below 1% with B8 regressions; a direct-integer weight fast path is slower despite exhaustive correctness.
  These variants remain unselected. [Raw decisions](evidence/2026-10-25-integer-prepacked/DECISION-01.md).
- B14 under preceding 97f62431 reaches B32 Smol/Tiny/Qwen 3141/1579/3126 token/s, about 10–15% over B22.
  This changes precision and is not a free B22 optimization. Historical B14/FP32 token counterexamples remain.
  [Raw timing scope](evidence/2026-10-25-integer-b14-scheduling/README.md).

## Correctness and scope

Selected source passes 452 tests per GPU on each of four devices, full check-all and Linux packaging. Six new tree/error-semantic mutants are caught; the previous prepacking and planner mutation receipts remain separate. Weight conversion exhausts 1,017,852 finite FP16 value/row-exponent pairs per precision.
Parent/canonical seed 7001 at ±sigma 1e-3/restored prefill, token/text/reward and exact restore match the preceding B22
source on all three trained models. This finite corpus does not establish general model quality.

Native Windows source also passes 452 tests. Four pinned tiny layouts, both precisions and parent/changed/restored
match Linux 5070 Ti exactly, including portable identities and logits/token/cache hashes.
[Exact source comparison](evidence/2026-10-25-attention-tree/native-windows-comparison-01.json).
All three trained models now match across 5070 Ti/3060 for parent/canonical±/restore, complete consumed-file
manifests, portable identities, prefill hashes, tokens/text/rewards and weight hashes. General quality and managed
lifecycle/ownership remain open. [Trained cross-GPU scope](evidence/2026-10-25-attention-tree/selected-trained-comparison-01.json). vLLM batch invariance describes
batch size/order stability; it is not evidence of equality across heterogeneous GPUs under our strict contract.
[Official scope](https://docs.vllm.ai/en/latest/features/batch_invariance/).

## Exact receipts

- [Selected source and trained comparisons](evidence/2026-10-25-attention-tree/SELECTED-RESULTS-01.md),
  [selection and rejected variants](evidence/2026-10-25-attention-tree/DECISION-01.md).
- [Earlier conversion/grouping and native Windows receipts](evidence/2026-10-25-integer-conversion/README.md).
- vLLM default: [Smol](evidence/2026-10-25-strict-overnight/bench-smollm-vllm-nhan-01.json),
  [TinyLlama](evidence/2026-10-25-strict-overnight/bench-tinyllama-vllm-nhan-01.json),
  [Qwen](evidence/2026-10-25-strict-throughput/bench-vllm-nhan-01.json).
- vLLM batch-invariant: [Smol](evidence/2026-10-25-strict-overnight/bench-smollm-invariant-nhan-01.json),
  [TinyLlama](evidence/2026-10-25-strict-overnight/bench-tinyllama-invariant-nhan-01.json),
  [Qwen](evidence/2026-10-25-strict-throughput/bench-vllm-invariant-nhan-01.json).
