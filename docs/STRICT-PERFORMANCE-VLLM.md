# Strict performance: vLLM source review and implications

The owner asked to compare with vLLM, read its repository and prioritize general model/GPU support rather than
optimizing a single Qwen checkpoint. The repository was inspected at
[`e7473bf6862289f0647d1f4b01498288b181e063`](https://github.com/vllm-project/vllm/tree/e7473bf6862289f0647d1f4b01498288b181e063),
2026-10-24. The installed comparison package is vLLM 0.32.0; exact selected source hashes are in the benchmark
receipts. A current source tree and an installed release are distinguished deliberately.

## What the source actually does

| Source at the pinned commit                                                                                                                                        | Finding and consequence for HeteroES                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Qwen2 model](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/models/qwen2.py)                              | Fuses QKV and gate/up projections and passes packed token positions. Transfer execution fusion through original weight pointers; do not introduce a repacked model copy that misses ES perturbations/restores.                                                                              |
| [Deterministic projections](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/determinism/batch_invariant.py) | Persistent tiled matrix multiplication uses `tl.dot` and fixed configurations. Batch invariance alone does not specify the same instruction/reduction sequence on heterogeneous architectures. This is a throughput reference, not a drop-in replacement for the current strict arithmetic. |
| [Scheduler](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/v1/core/sched/scheduler.py)                                    | Assigns a token budget per iteration, allowing multiple requests to advance together. Pack independent sequence work and compact completed rows before building a wider serving scheduler.                                                                                                  |
| [CUDA Graph wrapper](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/compilation/cuda_graph.py)                            | Dispatches capture/replay by a batch descriptor. Stable input buffers are the caller's responsibility. ES needs stable live-weight pointers, fresh per-candidate KV and deferred arithmetic-error checking; graph reuse must not freeze stale weights.                                      |
| [RoPE](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/layers/rotary_embedding/base.py)                     | Computes and registers cached tables. Adopt table lifetime, while retaining canonical frequency bits and specified sine/cosine instead of vendor transcendentals.                                                                                                                           |
| [KV manager](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/v1/core/kv_cache_manager.py)                                  | Manages block ownership, allocation and prefix reuse. A future ES prefix cache must include model/parent/candidate/backend identity or be cleared; matching prompt tokens do not justify reuse after perturbation.                                                                          |
| [Determinism tests](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/tests/v1/determinism/test_batch_invariance.py)              | Tests batch-one versus batched logprobs, prefill/decode and quantization effects. Adopt these test categories across graph families and supported GPU builds.                                                                                                                               |

The official [reproducibility documentation](https://docs.vllm.ai/en/stable/usage/reproducibility/) limits its guarantee
to the same hardware and vLLM version, even with deterministic scheduling/batch invariance. The earlier 208-prompt
cross-GPU counterexamples remain in the [original evidence](evidence/2026-10-24-vllm-probe/README.md).
No new finite passing matrix erases those counterexamples or qualifies an untested build.

## Relevant papers and technical material

- [PagedAttention, SOSP 2023](https://arxiv.org/abs/2309.06180): memory-efficient KV ownership and sharing permit
  larger effective batches. Its serving results use different models/hardware/workloads; published speedups are
  not HeteroES acceptance numbers. Our immediate transfer is packed sequence execution; paged allocation remains open.
- [FlashAttention](https://arxiv.org/abs/2205.14135): tiling reduces transfers between device memory and on-chip
  storage. Its use of “exact” means attention without the algorithmic approximation of sparse methods. The official
  [tests](https://github.com/Dao-AILab/flash-attention#tests) use numerical tolerance; this does not promise our fixed
  FP32 tree's bit pattern or heterogeneous token equality. Borrow storage/work partitioning after arithmetic proofs.
- [Defeating Nondeterminism in LLM Inference](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/):
  reductions in RMSNorm, matrix multiplication and attention must remain independent of batching and sequence
  slicing. Different tensor-core instructions can imply different reduction orders. This supports explicit operator
  contracts and prefill/decode/compaction tests; a deterministic scheduling flag is insufficient.
- [vLLM CUDA Graph design](https://docs.vllm.ai/en/latest/design/cuda_graphs/): pure decode can use full capture,
  while mixed/prefill batches need different capture capabilities. Start with bounded decode buffers and an explicit
  dispatch key rather than capturing arbitrary Python control flow.

## Why Tensor Cores need their own numerical design

The [NVIDIA PTX MMA specification](https://docs.nvidia.com/cuda/parallel-thread-execution/index.html#warp-level-matrix-instructions-mma)
leaves FP16/BF16/TF32 MMA accumulation order, rounding and subnormal handling unspecified. Substituting such an
instruction for our explicitly rounded product/tree sequence therefore needs a new coverage argument. This is a
constraint on the current numerical contract, not a proof that strict inference can never use Tensor Cores.

[DGEMM on Integer Matrix Multiplication Unit](https://arxiv.org/abs/2306.11975) and
[Ozaki Scheme II](https://arxiv.org/abs/2504.08009) explore floating-point matrix multiplication built from lower-
precision/integer matrix products. They are useful research leads for a future separately versioned backend.
The [error analysis](https://arxiv.org/abs/2506.11277) warns that poorly scaled rows/columns can impair accuracy or
require many component products. High accuracy alone also does not reproduce our particular FP32 reduction tree.

At that source-review checkpoint no integer/Tensor-Core backend was implemented or qualified. Before adopting one, specify conversion and
reconstruction, overflow/range rules, row independence and bounded workspace; build an independent oracle; then
measure token behavior, ES perturbation sensitivity, exact restore and heterogeneous model/GPU performance.
Published FP64 emulation results are not LLM or HeteroES acceptance receipts.

## What was implemented and what the measurements mean

The [shared decoder contract](../runtime/docs/strict-decoder-v1.md) now covers three graph families and four layouts,
including untied heads, biases and query width different from hidden width. Row tiling, cached canonical RoPE and
packed causal attention operate below checkpoint selection. No new managed backend/default was enabled.

[Benchmark receipts](evidence/2026-10-25-strict-throughput/README.md) use the same token inputs, FP16 storage,
fixed greedy output budget, no EOS stopping, no prefix reuse, one excluded warmup and repeated synchronized host
measurements. All engines use a single trained checkpoint for that controlled comparison. Graph-family coverage
comes from separate small CPU/GPU fixtures and must not be presented as trained-model performance evidence.
The environments differ (including CUDA/Torch/Transformers builds), and GPUs are not otherwise isolated.
For this fixed-batch comparison, prefix caching is disabled and the requested batch fits in memory. Continuous
batching and paging explain vLLM's broader serving capacity; the immediate targets for this measured gap are
projection throughput and launch overhead.

Intermediate measurements are retained: packing improved throughput, while reducing KV concatenation from 133 to
five calls in a two-layer/32-sequence fixture gave only a small additional end-to-end improvement. Synthetic linear
sweeps then isolated a much larger projection cost. Weight-only shared staging regressed some cases; staging both
weights and activations improved the tested widths on both architectures, without changing reduction trees.

The next heavy performance work is projection arithmetic/memory throughput, guided by
operator and end-to-end profiles. More Python orchestration changes alone cannot be assumed to close the tensor-core
throughput gap. Keep model adapters, arithmetic and execution tuning separate; new graph operations require a new
coverage argument, and every supported architecture/build still needs qualification. The full M0–M6 plan is open.

## Captured decode continuation

The [overnight continuation](evidence/2026-10-25-strict-overnight/README.md) adds dimension-selected independent
subtrees and a single bounded decode capture, with stable original-owner KV slots, EOS compaction and error-checked
publication. Captures read the original live weights, invalidate on parameter rebinding/stream/capacity changes,
and clear KV/selector content at request boundaries. No managed default is enabled.

Profiles of one-layer random layouts at hidden widths 512/1024/1536 show projections accounting for approximately
93–99% of CUDA kernel time at batch 32. These are graph-layout measurements, not trained-model performance evidence.
The same controlled trained-checkpoint workload improves from 100.5/334.6/379.8 to approximately
209.9/422.6/500.7 total tokens/s at batch 1/8/32 on the local 5070 Ti. The prior vLLM default comparison is
518.7/4037.9/13802.5, and batch-invariant is 146.0/1164.5/4697.2. Library builds and measurement stages differ;
neither the single-request improvement nor finite passing fixture matrix closes the large-batch gap.

Native FTZ multiplication was explicitly examined instead of assumed equivalent. In 3,139,288 finite input pairs,
17 multiplication results differ on each surveyed architecture; the boundary study includes
`0x00800000 * 0x3f7fffff`, where round-then-flush yields the smallest normal and native FTZ yields zero.
Unrestricted native FTZ multiplication was rejected. The selected kernels retain integer signed-zero flushing.
Smaller-tree, split-K and matrix-tile prototypes, including slower variants, remain in the receipts.

Further speed work must still preserve the present reference or introduce a separate fully specified numerical
backend/reference, as ADR-012 permits. An integer Tensor Core prototype needs bounded accumulation/reconstruction,
independent CPU answers, trained parent/perturbation comparisons and cross-GPU evidence before adoption.
The published integer-emulation papers remain research leads, not acceptance of an implementation.

## Separately versioned integer continuation

`fb18a7b7` adds an experimental row-scaled integer projection and captured decoder with its own independent CPU
reference. B14/B22 precision, exact RNE quantization, nonoverflowing integer MMA/int64 reconstruction and final scaled
RNE/FTZ encoding are specified in the [contract](../runtime/docs/integer-projection-v1.md). The old FP32 tree is retained
under its existing operator identity. There is no full quantized or FP32 second weight matrix; small row-scale metadata
is refreshed from live FP16 weights at every locked generation entry and cleared at exit. No managed default changes.

The [new receipts](evidence/2026-10-25-strict-integer/RESULTS-01.md) use the same eight tokenized prompts, 32 generated
tokens, FP16 storage, context limit 512, one excluded warmup and median of three synchronized host measurements.
The comparisons below use the prior vLLM default receipts and separate unisolated process runs/builds. Consumed model
asset hashes and workloads match; prior Smol download metadata prevents claiming identical *full* manifests there.

| Model on 5070 Ti | B22 token/s, B1 | B22 total token/s, B32 | B32 vs prior FP32 | B32 vs vLLM default |
| --- | ---: | ---: | ---: | ---: |
| SmolLM2-360M | 177.1 | 1318.2 | 1.64x | 9.1% |
| TinyLlama-1.1B | 114.5 | 830.7 | 2.88x | 10.7% |
| Qwen2.5-0.5B | 171.8 | 1358.5 | 2.71x | 9.8% |

B1 regresses to 74–86% of the previous FP32 backend. B22 on the 3060 reaches 663.6/613.1 total token/s at B32 for
Smol/Qwen, compared with 211.6/157.7 previously. These results do not meet the near-vLLM objective. Scalar weight
conversion and tile reuse remain performance targets; lowering precision alone was not consistently faster.

Parent and a canonical antithetic seed pair (`7001`, sigma `1e-3`), followed by exact restore, were checked on all
three local trained models. B22 matches their FP32-tree token streams on this finite corpus. B14 changes one Qwen
minus-candidate stream and has larger prefill errors; this counterexample is retained. Neither result establishes
general model quality or an all-input equivalence to the old tree. Smol/Qwen parent/candidate logits, tokens, text,
reward and weight hashes match between 5070 Ti and 3060 with the same new full asset manifests/source identities.
TinyLlama's trained cross-GPU check and native Windows remain open.

A scratch-only conversion prototype changes the FP16 exponent bits exactly and uses PTX integer RNE conversion.
It exhaustively matches admitted finite FP16 value/row-exponent pairs and improves the surveyed single-row operator
by roughly 1.2–1.6x on Nhut's 5070 Ti. Trained scratch B22 B1/B32 results are 249.4/1451.6 (Smol), 174.4/918.9
(TinyLlama) and 254.7/1507.7 (Qwen), with the same finite logits/tokens/restore results as the integer baseline.
It remains unselected and unqualified. The selected
baseline, rejected vector-load/control-code attempts, compiler audits and mutation failures are preserved separately.
