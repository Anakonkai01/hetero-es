# Source mechanisms used for the output-parallel LoRA experiment

This extends the earlier [engine audit](../../../strict-engines-source-audit-2026-10-25.md), rather than
replacing its pins or copying its vendor arithmetic. The owner requested reference to vLLM, SGLang and
TensorRT-LLM during this continuation. Source copies here are inspection receipts; runtime code does not
import them. The new CUDA code independently implements HeteroES's existing arithmetic.

| Engine / exact source inspected | Mechanism | Decision in this experiment |
| --- | --- | --- |
| [vLLM LoRA expand](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/lora/ops/triton_ops/lora_expand_op.py), commit `e7473bf6862289f0647d1f4b01498288b181e063` | Tiles output rows/columns and groups LoRA slices; expand can add into the base output | Use output-dimension parallelism and retain the fused epilogue. Do not adopt `tl.dot` accumulation/casts as the strict reference. |
| [SGLang dense LoRA B](https://github.com/sgl-project/sglang/blob/main/python/sglang/kernels/ops/lora/dense/sgemm_lora_b.py), installed wheel `sglang==0.5.22` | Tiles tokens and output columns; computes the rank product, scale and base add in one kernel | The output dimension is much larger than rank. Test assigning independent output elements to threads while retaining the strict rank tree in registers. The mutable upstream link is navigation; the copied wheel file's SHA-256 pins the actual inspected content. |
| [TensorRT-LLM LoRA](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/lora/lora.cpp), `v1.2.1`, commit `376f7e1bd8ed543f75014309e3fd4b237e9b0e73` | A separate skinny shrink GEMM and grouped expand; first GEMM uses split-K | Keep shrink and expand as distinct profiling categories. Ordinary floating split-K is not adopted because its reduction must first be reconciled with the frozen strict tree. |

The derived hypothesis was specific to our measured workload: the preceding finish spent a full warp on
each rank-8 output and transposed the epilogue through shared memory. A per-output register tree can remove
the shuffle/barrier work and let neighboring threads write neighboring output elements. That is our
inference from the sources and profile, not a speed claim made by the upstream projects.

`fetched-01.json` pins the vLLM/TRT-LLM source copies. `sglang-pin-01.json` pins the installed wheel path,
version and file hash; no upstream commit is inferred from a wheel without VCS metadata.

The rank-32 SM86 regressions are preserved in the operator sweeps, and the selected decoder policy retains
the strict warp control for ranks above 16. No vendor fallback, model-name dispatch, lower precision or
arithmetic relaxation is hidden in the selected scheduling change.

## What this does NOT show

This is not an audit of every upstream engine/backend/version or evidence of their cross-GPU strictness.
The inspected source does not establish that any one upstream dispatch ran in a throughput receipt.
Actual matched vLLM controls, local operator results and real-model results have separate receipts.
