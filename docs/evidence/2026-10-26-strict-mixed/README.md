# Unselected asymmetric integer projection experiment

Continuation after vLLM impact survey `3ee55bbf`. The owner prioritized HeteroES's own strict kernels,
allowing separately identified arithmetic experiments while retaining heterogeneous-GPU reproducibility.
The production runtime is unchanged in this experiment.

The scratch kernel quantizes FP32 activations with the existing A22/A14 power-of-two rule and live FP16
projection weights with W6. This reduces the signed-byte MMA products from nine to three/two per dot tile.
It keeps one FP16 model, bounded operand scratch, exact integer sums and the existing RNE/FTZ output
encoding. It does not call vendor floating GEMM or materialize a full quantized model. W6 bounds each digit
by 64; per-degree sums are below 2^31 and total dots below 2^43 at the admitted maximum width. No clipping
or approximate float scaling is introduced. This is different arithmetic from B22, explicitly identified
as `row_scaled_mixed_integer_dot_v1_probe`; model usefulness requires its own gate.

An independent Fraction quantizer tests ties, signed zero, FTZ and a known dot/bias. Six targeted tests
pass on each GPU host, including A22/W6, A14/W6, and unchanged-precision controls, odd widths, tails,
unaligned storage, bias and split-K. Fourteen operator shapes are measured on both hosts with raw timings
and identities. These finite operator results do not qualify an end-to-end decoder across architectures.

The Qwen whole-model pilot retains the original B22 LM head and shares one model across three graph
variants. Same eight prompt pool, context 512, 32 greedy output tokens, ABCCBA ordering and ten host-wall
observations per variant. Each execution repeats its own output exactly; cross-variant outputs may differ.

| Batch | B22 token/s | A22/W6 | Ratio | A14/W6 | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 276.9 | 276.6 | 0.9991 | 275.4 | 0.9946 |
| 8 | 1467.8 | 1431.6 | 0.9754 | 1511.9 | 1.0301 |
| 32 | 3758.2 | 3864.8 | 1.0284 | 4057.3 | 1.0796 |

The gain is insufficient to select a different arithmetic contract in this continuation. It still falls
far short of the approximately 13835 token/s vLLM reference. Only two of eight batch-8 output rows equal
B22; this is not itself a quality defect under D4, but no trained quality/candidate gate was completed.
No defaults, precision admissions, native packages or historical recipes are changed. The next experiment
returns to the unchanged B22 arithmetic and tests raw-weight prefetch scheduling.

## What this does NOT show

No selected optimization, near-vLLM result, broad quality, trained cross-GPU decoder equality, native
Windows acceptance, managed lifecycle or learning. Operator speedups cannot substitute for whole-model
results or compensate for an unmeasured usefulness gate. Unfavorable results are retained.
