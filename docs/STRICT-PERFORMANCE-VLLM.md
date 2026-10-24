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

No integer/Tensor-Core backend was implemented or qualified here. Before adopting one, specify conversion and
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

The next heavy performance work is projection arithmetic/memory throughput and bounded decode capture, guided by
operator and end-to-end profiles. More Python orchestration changes alone cannot be assumed to close the tensor-core
throughput gap. Keep model adapters, arithmetic and execution tuning separate; new graph operations require a new
coverage argument, and every supported architecture/build still needs qualification. The full M0–M6 plan is open.
