# Whole request controls and alternative strategies, 2026-10-27

The primary goal remains Qwen B32 short32 at nearly 80% of the matched vLLM control while preserving B22
results and flags. These controls test where the time goes and whether larger strategy changes help.
All curves use the same prompts, prefix caching **off**, EOS stopping **off**, greedy selection, and five
samples. No repeated-prompt deduplication or prefix memoization was introduced.

| Engine/source | 1 token ms | 8 tokens ms | 32 tokens ms | 128 tokens ms |
| --- | ---: | ---: | ---: | ---: |
| B22 `267ba0b5` | 37.13 | 53.38 | 109.10 | 346.97 |
| vLLM matched control | 13.26 | 26.75 | 74.05 | 263.97 |
| Existing B14 | 32.24 | 48.76 | 105.99 | 348.99 |
| Fast-convert B14 prototype | 29.12 | 45.23 | 101.72 | 341.18 |
| Mixed MLP B14, attention/head B22 prototype | 31.32 | 46.82 | 101.63 | 334.40 |

Raw curve JSON contains complete token IDs, identities and equality across output-length prefixes. One
token includes request setup, prefill, first selection and publication, so it is not pure prefill kernel
time. Roughly two thirds of the 32-token B22 gap is already present in the one-token request. Profiling
corroborates prefill projection cost: before the first decode-layout event, streamed integer projection
accounts for **22.2 ms**, versus **2.46 ms** for prefill attention. Profile durations include instrumentation
and are not substituted for exclusive wall timings.

## Captured prefill retry

A new harness adapts the old capture idea to current deferred-error and graph lifecycle APIs. It validates
the caller's inputs, owns static input/layout/flag buffers, preserves caller flags, falls back for unsupported
calls, clears retained request buffers, and uses one primary model. Eager/captured token outputs agree and
the warmed capture count is stable. ABBA controls in `capture-b22-02.json` show **109.203 → 108.914 ms** for
B22 short32 (+0.27%); B14 **102.295 → 101.570 ms** (+0.72%). Reject as a material architecture gain. The
first launch failed at a brittle B22-only source extraction marker after fast-convert source was generalized;
its log is retained, and the next frozen source stage fixes that marker. No old evidence was edited.

## Mixed arithmetic research

The mixed prototype has an explicit new identity: MLP projections B14; attention and lm_head B22; original
strict FP32 nonlinearities. Precision follows module role for both prefill/decode and cached/uncached calls.
It shares one live FP16 model, partitions refreshed exponent metadata, and refuses cross-precision tied
weights. Three tiny architecture fixtures compare cached/uncached parent and in-place changed weights with
an independent CPU mixed reference; **3 pass**. Despite faster long generations, short32 reaches only
**10075.5 token/s (72.8% of 13834.6)**. It changes the B22 contract and does not close the primary goal.
No full mixed-quality survey or native qualification was attempted after this speed gate.

The [separate precision survey](../2026-10-27-strict-precision-quality/README.md) records finite B14 quality
differences and cross-GPU consistency. The [bounded packing pilot](../2026-10-27-strict-prefill-prepack/README.md)
tests another strategy while preserving B22 and is rejected at its operator gate.

## What this does NOT show

Alternative precision rows are **not** bit-equivalent B22 results, a new default, quality acceptance or a
shortcut to the 80% goal. Longer-output ratios do not replace the short32 objective. Capture and mixed
prototypes remain standalone research with incomplete resource/failure/platform gates. No learning,
managed lifecycle, installer, deployment or lab-state change is claimed.
