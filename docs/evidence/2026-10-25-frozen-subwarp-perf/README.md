# Strict frozen-base adapter execution, 2026-10-25

Selected source: `20856dea51e1c8590a56bc573e55d8820b02827a`, following the early unsupported-rank
guard in `2cde05d5`. This is the earlier LoRA work in this continuation. The owner's subsequent priority
is the full-weight B22 core; its new measurements are in
[`../2026-10-25-b22-core-perf/`](../2026-10-25-b22-core-perf/README.md).

The selected finish assigns independent output elements to threads and reproduces the strict 32-lane
rank tree in registers, including negative-zero padding subtrees. It removes shuffle/shared epilogue
work without adopting upstream floating-point dot arithmetic. Ranks at most 16 select this execution;
ranks 17–32 retain the warp execution because the rank-32 SM86 sweep regressed. CUDA ranks above 32
fail before graph setup; the CPU reference remains separate. The inspected vLLM/SGLang/TensorRT-LLM
mechanisms and exact source pins are in [source-audit/README.md](source-audit/README.md).

## Matched model results

One primary model weight set, two bounded graph workspaces, context 512, greedy 32 output tokens,
eight fixed prompts repeated to batches 1/8/32. ABBA has one warmup and five timed observations per
stage: ten host-wall observations per execution. Refresh stays inside each generation call. The
control is explicit strict warp execution, not HF or full-weight B22.

The nonzero probe-adapter batch-32 medians, total output tokens/s:

| Model | 5070 Ti warp | 5070 Ti selected | Gain | 3060 warp | 3060 selected | Gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SmolLM2-360M | 3075.2 | 3899.6 | 26.8% | 1162.0 | 1504.1 | 29.4% |
| Qwen2.5-0.5B | 2910.5 | 3622.8 | 24.5% | 1025.9 | 1275.1 | 24.3% |
| TinyLlama-1.1B | 1435.1 | 1607.5 | 12.0% | 438.7 | 494.2 | 12.6% |

Zero-adapter and batch-1/8 observations, all raw durations and spreads are retained. The independent
[model comparer](model-comparison-01.json) checks the pinned inputs and recomputes these medians.
Smol/Qwen have an int8 tied-head sidecar; Tiny retains its strict FP16 untied head. These are distinct
search spaces from full-weight B22.

## Numerical and source scope

Each bundle was built once on CPU, sealed and transferred byte-for-byte to the second host. The three
bundle manifests pin the frozen artifacts, adapter files, model files and schema. Zero, nonzero probe,
canonical plus and minus adapters produced equal token streams, decoded text, canned rewards and
prefill-logit hashes across both executions and both architectures. The comparer checks 5248 generated
token positions per model per host. Exact adapter restoration and unchanged frozen files are checked.
The probe adapter is synthetic; canonical perturbations are finite sensitivity checks, not training.

`selected-source-01.json` pins the runtime source at the selected commit. `raw/*-selected-paired-5070ti-01`
reruns local selected dispatch; `remote-selected-01/` preserves the matching source-stage remote receipts.
The original explicit execution comparisons are also retained under `raw/`.

Targeted CPU checks passed (99 tests). The selected GPU command passed 216 tests on each host; its
scope is recorded in the logs, not every repository GPU test. Five finish mutants were killed on scratch
copies. PTX/SASS and audit identities are retained under `compiled-sm120-02/` and `compiled-sm86-01/`.
The partial `compiled-sm120-01/` and failing log retain a private compile attempt without an active CUDA
context; the corrected harness creates that context explicitly.

Fresh vLLM controls are **unavailable**. Attempt 01 could not find CUDA_HOME/nvcc. Attempt 02 used
the already installed wheel toolkit with process-local CUDA_HOME, but FlashInfer sampling JIT failed.
Both failures and environments are preserved for both hosts. No environment, driver or SDK was installed
to chase those controls. Historical vLLM values are not denominators for this table.

Final repository and isolated Linux package checks for the subsequent B22 source are recorded in the
new B22 folder; they must not be represented as package checks of this older commit.

## What this does NOT show

No near-vLLM claim, broad model quality, learning, native Windows trained acceptance, managed lifecycle,
device approval or general hardware qualification. This finite two-host corpus does not prove every
adapter/rank/model or accepted input. `hardwareQualified` remains false. The later B22 source has separate
receipts and does not retroactively change the source identity of these results. No push, merge or deploy.
