# Shared strict decoder and throughput continuation (2026-10-25)

Owner resumed from clean `033065d`, prioritizing the strict kernel, then explicitly requested vLLM comparison,
repository/paper review and general model/GPU coverage. The full M0–M6 plan is unchanged and incomplete.
No push, merge, deployment, device-state change or learning run was performed.

## Final implementation

- `runtime/src/heteroes/eval/strict_cuda.py`: independent row tiles; coalesced weight/activation staging with
  padded shared rows, barriers between reuse phases and a 40 KiB staging cutoff; original arithmetic/tree retained.
  The wider fallback and capped grid-stride row traversal have GPU regression checks.
- `strict_decoder.py`: shared reference/CUDA graph adapters for a restricted Qwen2/Llama/Mistral operator graph.
  Explicit consumed-parameter/configuration checks, optional biases, tied/untied heads and independent query width.
  Unknown graphs, sliding attention, unsupported RoPE and unconsumed parameters fail. RoPE tables are bounded buffers.
- `strict_decoder_packed.py`: ragged packed prefill/decode, independent causal ranges and caches, greedy processing,
  EOS compaction and two KV concatenations per layer. No retained cache across generation/candidate calls.
- The old pinned-Qwen constructor is a wrapper around shared CUDA graph operations. All new backends remain
  experimental with `hardwareQualified: false`; no managed recipe or strict audit policy was activated.
- [Graph/arithmetic contract](../../../runtime/docs/strict-decoder-v1.md),
  [pinned vLLM source review and papers](../../STRICT-PERFORMANCE-VLLM.md).

`source-identity-final-01.json` pins final source/tests and confirms identical bytes in the fresh Linux package
workspace. Protected noise/ES/ledger/generation-record paths are unchanged from `033065d`.

## Final checks

| Receipt | Result and scope |
| --- | --- |
| `check-all-03.log`, `checks-03/` | **ALL PASS**: runtime CPU **2,943 passed / 211 skipped**, backend **452 passed**, one existing dependency warning; lint/format, source archives/imports, types/i18n, web/desktop units/builds, browser and Electron fixtures. |
| `gpu-final-{nhan,nhut,thao,quang}-01.log` | **215 passed per GPU** on the final source. Includes primitive bits, rounding/zero/domain failures, row/batch/stream independence, shared-memory cutoff/max-width/grid-stride, graph/cache/greedy/compaction and three graph families. |
| `families-{nhan,nhut,thao,quang}-03.json`, `families-comparison-03.json` | **All four equal**: four layouts (Qwen2, Llama, Llama with query width different from hidden width, Mistral), two weight states each, three ragged prompts. CPU reference, serial CUDA and packed logits agree; tokens/cache hashes/fixture restore agree. Each machine has 16 recorded builds; PTX and SASS audits are available and have zero violations. |
| `mutation-cpu-02.log`, `mutation-kernel-nhut-02.log`, `mutation-packed-nhut-03.log` | Final relevant controls pass; **7 + 8 + 8 = 23/23 mutants killed** on scratch copies. Includes graph refusal, head width, staged addressing, row ownership, causal/key ranges, fault reporting, cache/position/compaction and per-sequence-copy regression. Definitions are `mutants-{cpu-01,kernel-02,packed-02}.json`. |
| `linux-packaging-01.log` | Fresh isolated Linux source-copy package/build/import checks pass. Workspace: `.scratch/strict-throughput-linux-20261025`; tested source bytes match packaged bytes. This is not native Windows or packaged GPU execution acceptance. |
| `lab-status-final-01.json` | All three deployed lab services stopped. Read-only deployed head remains `82c37fcae4e643804a5f7e6d8e1147523516c88a`. |

Hardware: nhan/local and nhut are RTX 5070 Ti (`sm_120`, Linux); thao and quang are RTX 3060 (`sm_86`, WSL2).
The fixture probe uses random small models and a deterministic down-projection sign flip, not a trained-model
or canonical ES-candidate acceptance campaign. Script: `probe-families-01.py`; it imports the checked-in test factories.

## Controlled throughput comparison

`benchmark-comparison-01.json` verifies **identical model files, prompt token IDs and workload settings in all 13
receipts**. One pinned Qwen2.5-0.5B checkpoint is used solely as a controlled trained-model performance fixture.
Eight prompts repeat to fill each batch; greedy output is exactly 32 tokens per row; EOS stopping/prefix caching
are disabled. One warmup per batch is excluded, followed by three synchronized host-wall measurements; medians
include prefill, generation and engine overhead. Numbers are **total generated tokens/s across a batch**.

| GPU / implementation | Batch 1 | Batch 8 | Batch 32 |
| --- | ---: | ---: | ---: |
| 5070 Ti, starting strict source `033065d` | 73.5 | 67.3 | 67.4 |
| 5070 Ti, final shared packed strict | 100.5 | 334.6 | 379.8 |
| 5070 Ti, native HF FP16 | 181.4 | 1,207.6 | 4,243.4 |
| 5070 Ti, vLLM 0.32.0 default | 518.7 | 4,037.9 | 13,802.5 |
| 5070 Ti, vLLM batch-invariant | 146.0 | 1,164.5 | 4,697.2 |
| 3060 Thao, final shared packed strict | 43.0 | 105.6 | 110.1 |
| 3060 Thao, vLLM default | 246.9 | 1,673.3 | 4,904.6 |
| 3060 Thao, vLLM batch-invariant | 78.2 | 644.3 | 2,561.3 |

Final receipts: `bench-packed-{nhan,thao}-03.json`. Comparators: `bench-vllm-nhan-01.json`,
`bench-vllm-thao-02.json`, `bench-vllm-invariant-{nhan,thao}-01.json`, `bench-hf-nhan-01.json`.
The starting baseline is `bench-baseline-nhan-01.json`; its script snapshot is `benchmark-initial-01.py` and its
runtime source is the unchanged `033065d` tree. `qwen-baseline-nhan-01.json` separately retains an initial finite
parent/perturbed probe. `qwen-strict-{nhut,quang}-01.json` are intermediate serial probes, not final-source receipts.

The final 5070 Ti batch-32 result is about **5.6×** the starting baseline. It remains about **36× slower than
vLLM default** and **12× slower than vLLM batch-invariant** in this workload. No throughput threshold is accepted.
All final strict benchmark repeats and batch-versus-single token comparisons agree. Native HF has batch/single
differences in these receipts. Eight short prompts do not erase the earlier larger vLLM cross-GPU counterexamples.

Builds differ: strict/HF use Torch 2.13.0+cu132 and Transformers 5.17.0; vLLM uses Torch 2.13.0+cu130 and
Transformers 5.19.0 in separate existing environments. GPUs are not otherwise isolated. Peak memory is the calling
process's Torch allocator measurement; vLLM uses multiprocessing disabled and a configured 0.35 memory fraction.
This is not a minimum-memory or cold-start comparison. Lazy strict compilation happens before timed cases.

For this fixed-batch workload the requested batch fits memory and prefix reuse is disabled. Projection throughput
and launch overhead are the immediate targets; continuous batching/paging matter additionally for dynamic serving.

## How the performance change was selected

- `bench-strict-nhan-01.json`: cached RoPE plus row tiling improves batch-one throughput to 96.1 tokens/s, while
  sequences still run serially. `bench-packed-nhan-01.json` first reaches 208.6 total tokens/s at batch 32.
- `kv-profile-before-01.json`: 133 concatenations per decode in a two-layer/32-sequence fixture on Qwen2,
  Llama-wide and Mistral. The bounded-copy regression test now allows five. Packing the copies improves the measured
  full decoder only slightly (`bench-packed-nhan-02.json`: 212.1 tokens/s at batch 32), so it is not claimed as
  the main throughput solution.
- `linear-throughput-{nhan,quang}-01.json`: synthetic widths 768/1024/2048/4096, several output sizes, rows 1/8/32
  and row tiles 1/2/4/8. Each tile result equals the other tiles; sampled columns also match a CPU reference.
  Event intervals include host-launch gaps, and synchronized host timings are reported separately.
- `linear-coalesced-nhan-01.json`: weight-only staging regresses some cases. Its source is retained as
  `prototype-weight-staging-01.py`; it was not selected.
- `linear-coalesced-x-{nhan,quang}-01.json`: staging both operands improves the four tested batch-32/row-tile-4
  shapes by approximately **1.7–2.1× on 5070 Ti** and **1.6–2.5× on 3060**. Source prototype:
  `prototype-input-staging-01.py`. This design was then formatted, promoted and tested as the final source.
- `linear-resources-01.log` is a failed private diagnostic without an active CUDA context. `-02.log/.json` first
  allocates a CUDA tensor and queries the earlier row-tiling kernel; no local-memory spill was found in those cases.
  These are not final staged-kernel resource or cross-thread context-qualification receipts.

The source review identifies optimized matrix multiplication, fusion, stable buffers and CUDA Graph replay as
further work. Ordinary floating Tensor Core MMA does not specify our reduction tree; integer/component methods
are research leads, not implemented replacements. No exactness requirement was relaxed to make a timing pass.

## Retained intermediate failures and limits

`row-tile-red-01.log`, `rope-red-01.log`, `packed-red-01.log`, `generic-red-01.log`, `head-layout-red-01.log` and
`kv-copy-red-01.log` precede the respective behavior. `gpu-tests-nhan-01.log` retains an obsolete expected build
name after row specialization; numerical checks passed and the expectation was updated. Early nhut/thao test runs
lacked the pure-Python `py` shim; it was copied into scratch test dependencies without installing into their envs.
`gpu-tests-quang-01.log` is an early partial capture; use the explicitly final log for that stage. The first Thao
vLLM command used a wrong venv path (`bench-vllm-thao-01.log`); the corrected path produced `-02.json`.

`check-all-01.log` and `check-all-02.log` pass earlier source stages; only `-03` is the full final-source run.
Earlier GPU/mutation/benchmark receipts remain dated stage evidence, not interchangeable with final receipts.
Raw log whitespace is retained. No earlier evidence or artifact folder was reformatted or rewritten.

## What this does NOT show

- No trained Llama/Mistral checkpoint or arbitrary model-family acceptance. These are three restricted graph
  adapters and four small layouts; scaled RoPE, sliding attention, MoE, quantization and LoRA remain unsupported.
- No universal bit-equality theorem or qualification of other NVIDIA architectures, compilers, drivers or OSs.
  Two GPU architectures and NVRTC 13.2 were exercised. WSL2 does not establish native Windows support.
- No managed lifecycle or physical-GPU ownership acceptance across worker/coordinator/profiling/export processes;
  no packaged GPU backend qualification. The experiments use live FP16 weights and bounded workspace in isolation.
- No learning/quality claim, full ES generation throughput, online serving latency, all-phase resource budget or
  accepted throughput target. The selected trained-model benchmark remains far below vLLM.
- No strict audit-policy activation, storage-loss/replacement-recovery acceptance, D10 recovery or watchdog closure.
  **M1, M2 and the full M0–M6 plan remain incomplete.**
