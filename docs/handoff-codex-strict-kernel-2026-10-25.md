# Shared strict kernel continuation — 2026-10-25

Source, tests, contract, vLLM review and immutable receipts are committed at **`a232ad0`**, on
`fix/human-review-single-model-2026-10-24`, after clean `033065d`. The following commit updates handoff/status only.
The full approved M0–M6 plan remains open; neither M1 nor M2 is complete.

## Owner direction and read order

The owner explicitly prioritized the kernel and system-defining work, requested vLLM benchmarking/source/paper
review, then emphasized that the implementation must generalize across models and GPUs rather than optimize only
Qwen. Continue that high-effort direction. Audit projection/API/UI is still reserved for a later medium session.

1. `AGENTS.md`, `docs/HANDOFF.md`, this file and [effort split](HUMAN-REVIEW-EFFORT-SPLIT.md).
2. [Shared decoder contract](../runtime/docs/strict-decoder-v1.md),
   [reference arithmetic](../runtime/docs/strict-reference-v1.md), ADR-012 and the numerical contract.
3. [vLLM repository review/papers](STRICT-PERFORMANCE-VLLM.md) and
   [evidence/limits](evidence/2026-10-25-strict-throughput/README.md).
4. Full plan: `/home/pc5070ti/projects/heteroes-review-2026-10-24/PLAN-SUA-HUMAN-REVIEW.md`.
   Earlier audit handoff: [xhigh safety checkpoint](handoff-codex-xhigh-human-review-2026-10-25.md).

## What changed

- Shared strict reference/CUDA graph adapters for restricted Qwen2/Llama/Mistral configurations. Explicit graph,
  shape, epsilon, bias, tying and consumed-parameter checks; no checkpoint-specific dimensions in the shared path.
  Query width can differ from hidden width. Unknown operations/configs fail instead of falling back.
- Canonical RoPE tables computed once and included in buffer inventory. Independent linear row tiles preserve
  product/tree/FTZ/bias order. Coalesced weight and activation staging reuses padded shared memory behind barriers,
  with a 40 KiB staging bound and a wider fallback. Grid-stride and cutoff/max-width cases are tested.
- Packed ragged prefill/decode, per-query causal/key ranges, independent call-local KV caches, greedy options,
  repetition penalty, explicit ties and EOS compaction. Two KV concatenations per layer; no candidate-spanning cache.
- Experimental identities include shared/packed/wrapper source and graph descriptors. Hardware qualification stays
  false. No managed recipe, SDK/API strict activation, legacy noise/ES/ledger/record behavior or device state changed.

## Measurements and limits

Final same-workload warm benchmark on 5070 Ti (total generated tokens/s): starting strict **73.5 / 67.3 / 67.4**
at batch **1 / 8 / 32**; final packed strict **100.5 / 334.6 / 379.8**. Batch 32 improves approximately **5.6×**.
vLLM default is **518.7 / 4,037.9 / 13,802.5**; batch-invariant is **146.0 / 1,164.5 / 4,697.2**.
Final 3060 Thao strict is **43.0 / 105.6 / 110.1**. Builds differ and GPUs are not isolated; read the full table.

The benchmark fixes prompt token IDs, model files, FP16 storage, greedy 32-token output, no EOS stopping/prefix
reuse and three repeats after warmup. `benchmark-comparison-01.json` checks all 13 receipts' workloads.
`trained-parent-comparison-01.json` also confirms final parent tokens match on the two GPU architectures for the
eight benchmark prompts. This is one trained checkpoint; no trained Llama/Mistral or universal equality claim.

Synthetic widths 768/1024/2048/4096 isolate projection costs independently of model choice. Weight-only shared
staging regressed some cases; the selected two-operand design improves tested batch-32 shapes by about 1.7–2.1×
on 5070 Ti and 1.6–2.5× on 3060. KV copy batching reduces operation count substantially but yielded only about
2% full-decoder improvement; do not keep treating copies as the whole gap. Current FP32 scalar projections and
launch costs remain much slower than vLLM's optimized matrix path. No performance threshold was accepted.

vLLM repository pinned/read at `e7473bf6862289f0647d1f4b01498288b181e063`, installed comparison version 0.32.0.
The note links source for projections, fused weights, RoPE, scheduler, KV, graph replay and determinism tests.
NVIDIA's floating MMA contract leaves accumulation order/rounding/subnormal handling unspecified. Integer/component
Tensor Core methods (Ozaki/Ozaki-II and error analysis) are research leads only: none was implemented, benchmarked
for LLM quality, or accepted as matching the present FP32 tree. Do not replace arithmetic under an existing identity.

## Verification

- Full final `check-all-03.log`: **ALL PASS**. Runtime CPU **2,943 passed / 211 skipped**; backend **452 passed**,
  one existing dependency warning. Source archive/import, lint/format/types/i18n, browser and Electron fixtures pass.
- Final source: **215 tests per GPU** on local/Nhut 5070 Ti (Linux), Thao/Quang 3060 (WSL2). Four small layouts,
  three graph families, two weight states each match CPU/serial/packed logits, tokens/cache hashes and fixture restore
  across all four machines (`families-comparison-03.json`). All recorded PTX/SASS audits have zero violations.
- Scratch mutations: CPU 7/7, final kernel 8/8 and packed/cache/compaction 8/8, **23/23**. Intermediate red tests,
  setup failures, slower prototypes and earlier source-stage runs are preserved and explained.
- Fresh Linux source-copy package/build/import checks pass at `.scratch/strict-throughput-linux-20261025`.
  `source-identity-final-01.json` proves exact runtime bytes match packaged bytes. No native Windows or packaged GPU
  execution qualification. Protected numerical directories and generation record remain unchanged from `033065d`.
- All owned check/probe/mutation/package command chains returned terminal status. Read-only deployed head remains
  `82c37fca`; all three lab services stopped. No live worker/lab environment, approval/contribution or driver changed.

## Next heavy work

1. Profile shared projection throughput and end-to-end decode across dimension/context/batch/architecture ranges.
   Extend the common operator implementation, rather than specializing on a Qwen checkpoint. Preserve the current
   tree/rounding/error contract and bounded workspace. Broader trained models need separate correctness/quality receipts.
2. Reduce launch overhead with stable bounded token/KV/argument buffers and decode CUDA Graph dispatch. Keep arithmetic
   error collection checked before results are published. Captured weights must remain live original pointers through
   ES perturb/restore; cache content must not survive candidate mutation. Capture pools, lifetimes, context/thread use,
   cache growth/compaction and memory limits require tests. Full-role physical GPU ownership remains an M4 gate.
3. If exploring integer/component Tensor Core arithmetic, create a separate numerical reference/version. Specify
   input conversion, range/overflow/reconstruction and reduction behavior; examine badly scaled inputs and the number
   of component products, then measure accuracy, tokens, perturbation sensitivity, memory and throughput. Published
   HPC throughput/accuracy is not evidence for this system or for the current FP32 tree.
4. Expand operator/config coverage deliberately: scaled RoPE, sliding attention, other families, quantized frozen
   base/LoRA and native Windows are not currently admitted. Do not qualify by a matching shape/model hash alone.
5. Preserve the remaining plan: M2 progress watchdog/hard caps and persisted D10 recovery; M3 bounded recovery I/O,
   dependency retention and audit sidecar/replacement reconciliation; M4 qualification/lifecycle/native packaging;
   M5 system acceptance and M6 quantized-base/LoRA. Medium audit projection/UI remains independent follow-up work.

## Operations and authorization

The owner explicitly renewed local GPU and SSH/GPU access to Nhut and both 3060 hosts in this conversation. No sudo
was needed. This handoff itself is not a new hardware authorization; apply current AGENTS and session instructions.
Use explicit GPU opt-ins and fresh scratch; leave enrolled workers and existing environments alone, especially `ai`.
No push, merge or deploy. Do not start the stopped lab merely to continue coding. Do not use Archive or `/mnt/sekai`.
Keep existing evidence immutable and preserve failures/platform limits. Commit logical groups; speak briefly in Vietnamese.
