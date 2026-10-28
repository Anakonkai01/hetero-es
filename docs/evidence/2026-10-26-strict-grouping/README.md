# Unselected contiguous integer projection grouping

Runtime base `b1ef257a`; no selected runtime changes. This scratch graph binds disjoint Q/K/V and
gate/up parameters to adjacent views of one primary allocation, preserving Parameter objects, shapes,
bits and schema. Only the storage/alias guards from the experimental FP16 graph are reused. Projection
execution still calls HeteroES's exact integer kernels. No vendor GEMM or second model is used.

Two B14/B22 tiny Qwen-layout tests match the independent CPU decoder through change and exact restore.
The trained Qwen pilot shares one model across prior and grouped graphs. Both variants repeat identical
tokens on the fixed eight-prompt pool, context 512, 32 outputs, ABBA and ten host-wall samples each.

| Batch | Prior token/s | Grouped token/s | Gain |
| --- | ---: | ---: | ---: |
| 1 | 276.8 | 306.1 | 10.59% |
| 8 | 1869.1 | 1944.3 | 4.03% |
| 32 | 4358.4 | 4495.8 | 3.15% |

This remains unselected pending broader lifecycle, architecture and candidate acceptance. The batch-32
gain alone does not justify changing the selected storage/ownership path in this increment.

A separate diagnostic wraps the existing ungrouped B22 captured step with external CUDA event nodes.
Across ten repeats, the final batch-32 Qwen step measures about 5.826 ms: gate/up 1.477 ms, down 0.986 ms,
attention 1.105 ms, QKV 0.590 ms, output projections 0.336 ms and LM head 0.703 ms. Event nodes perturb
scheduling; these scopes guide further work and are not an uninstrumented throughput measurement.
The MLP projections account for about 42% and attention 19% of this diagnostic step.

External timing events follow the documented capture mechanism in
[PyTorch Event](https://docs.pytorch.org/docs/stable/generated/torch.cuda.streams.Event.html) and the
[vLLM capture utility](https://docs.vllm.ai/en/latest/api/vllm/benchmarks/forward/capture/).

## What this does NOT show

Selected grouping, native Windows acceptance, trained cross-GPU candidate parity, broad quality,
managed ownership qualification, near-vLLM speed or learning. No push, merge or deployment occurred.
