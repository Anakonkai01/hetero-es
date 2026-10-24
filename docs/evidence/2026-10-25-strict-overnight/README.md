# Strict performance continuation — 2026-10-25

Starting point: clean `81110a14`. The owner explicitly requested unattended continuation of the full M0–M6
plan, with the highest priority on general strict performance approaching vLLM. Existing local/remote GPU
authorization remains in force. No push, merge, deployment, device state change or learning run is authorized
by this work. Receipts are added once and never overwritten.

This folder records experiments as they happen; final selections and verification will be added separately.
The previous strict-throughput evidence remains immutable.

## Selected implementation

- `strict_cuda.py` version 3 selects smaller per-thread subtrees and row tiles from matrix dimensions. Weight
  pointers, FP16 storage, separate rounded multiply/add, integer signed-zero FTZ and the adjacent-pair tree stay intact.
- `strict_decoder_graph.py`/`strict_decode_cuda.py` add bounded fixed-slot KV and one retained decode CUDA Graph.
  Original sequence owners survive query compaction; live in-place weight changes remain visible. Parameter
  rebinding, stream/capacity changes and failed computation invalidate capture. All KV/seen/selector state is cleared
  at request boundaries, on the correct owning stream when releasing. Errors accompany IDs in one ordered publication.
- Generation validation is shared with packed execution. Greedy ties, repetition penalty (including a Python penalty
  that rounds to 1 in FP32), left padding, EOS and the existing noncached path preserve the reference semantics.
- Additional tensor-payload admission includes both KV forms, actual packed prefill scratch, decode temporaries,
  warmup snapshots and a margin. This is not a global-device VRAM limit or managed physical-GPU ownership.
- The approved full [M0–M6 plan](../../PLAN-SUA-HUMAN-REVIEW.md) is now stored in-repo as an exact byte snapshot;
  `plan-snapshot-01.json` identifies its original source/hash. Its scope and unfinished milestones are unchanged.

## Current verification

- `gpu-graph-nhan-03.log` and `gpu-graph-{nhut,thao,quang}-02.log`: **255 tests per GPU** on current source.
  `graph-families-*-02.json` and `graph-families-comparison-02.json`: four layouts, two finite weight states,
  CPU/serial/packed prefill and captured logits/tokens agree across all four machines. Each target records **30
  audited builds**, with PTX and SASS available and zero reported violations. Exact fixture restore is checked.
- Direct tests compare post-decode KV bits with CPU, including reordered/compacted owners; clear candidate state;
  inspect live/rebound weights; and reject captured arithmetic errors before publication. Stream-release, prefill
  budget and inference-tensor cleanup regressions have preserved red receipts and corrected runs.
- `check-all-02.log` is the final complete CPU/product check; `check-all-01.log` is the earlier source stage.
  `linux-packaging-02.log` and `source-identity-02.json` verify fresh Linux source-copy packaging and byte identity.
  Protected noise/ES/ledger/generation-record files remain unchanged from `81110a14`.
- Final scratch mutations: `mutation-cpu-02.log` **3/3**; `mutation-gpu-nhut-02.log` **10/10**. The earlier 9/9 GPU
  group predates the explicit stream-owner regression. Definitions are retained alongside their logs.

## Performance and experiment interpretation

Profiles (`profile-baseline-nhan-02.json`) use random one-layer layouts at hidden widths 512/1024/1536. At batch 32,
projection kernels consume approximately 93–99% of recorded CUDA activity. CPU gaps and profile instrumentation
are distinct from CUDA activity; this is not a trained-model or serving profile.

The controlled Qwen2.5-0.5B comparison retains the prior eight prompts/token IDs, FP16 storage, greedy 32-token
output, no EOS stopping/prefix reuse, one excluded warmup and three synchronized host-wall repeats. Batch 32 repeats
those eight prompts four times. Current local graph receipt: `bench-graph-nhan-03.json`.

| 5070 Ti, total generated tokens/s | Batch 1 | Batch 8 | Batch 32 |
| --- | ---: | ---: | ---: |
| Previous packed strict (`81110a14`) | 100.5 | 334.6 | 379.8 |
| Smaller trees only (intermediate) | 102.1 | 411.6 | 485.2 |
| Current captured strict | 209.9 | 422.6 | 500.7 |
| Prior vLLM 0.32.0 default | 518.7 | 4037.9 | 13802.5 |
| Prior vLLM batch-invariant | 146.0 | 1164.5 | 4697.2 |

The new graph path improves single-request overhead substantially, while the large-batch gap remains about 28×
against default vLLM on this workload. The current graph process peaks near 1.53 GB Torch allocated (1.71 GB reserved),
including fixed KV/capture storage; this is not a minimum VRAM requirement or total process/driver peak. Library builds
and measurement stages differ, and GPUs were not isolated. No performance threshold is accepted by these results.

`trained-model-downloads-01.json` pins SmolLM2-360M-Instruct and TinyLlama-1.1B-Chat-v1.0 for broader trained-model
checks. Their `bench-smollm-*`/`bench-tinyllama-*` receipts are separate per-model controls, not interchangeable
workloads or automatic graph-family acceptance. No Mistral trained checkpoint acceptance is inferred.

`trained-benchmark-comparison-01.json` checks matching model asset hashes, prompt token IDs and workload settings within
each checkpoint. Current strict parent tokens agree on 5070 Ti/Thao 3060 for Qwen and SmolLM; TinyLlama was measured
locally only. Every current strict repeat and batch/single comparison passes. These are parent-only throughput runs.
SmolLM's local snapshot also contains one `.cache/huggingface/trees/<revision>.json` download-metadata file absent
from the remote copy. All other model-file hashes match. This explicit exclusion establishes identical inference
assets, not equal full registration documents; no managed qualification is inferred from it.

| Local 5070 Ti, total generated tokens/s | Batch 1 | Batch 8 | Batch 32 |
| --- | ---: | ---: | ---: |
| SmolLM2-360M strict graph | 239.9 | 598.1 | 804.9 |
| SmolLM2-360M vLLM default | 529.2 | 4093.2 | 14429.4 |
| SmolLM2-360M vLLM batch-invariant | 173.8 | 1371.2 | 5339.8 |
| TinyLlama-1.1B strict graph | 133.3 | 255.3 | 288.8 |
| TinyLlama-1.1B vLLM default | 322.9 | 2330.6 | 7791.8 |

Thao 3060 strict graph reaches **113.0/150.6/157.7** on Qwen and **131.1/194.2/211.6** on SmolLM at batch 1/8/32.
The two larger trained layouts explicitly use a 4 GiB admission budget; actual allocation is reported separately.
Across these three local trained checkpoints, single-request throughput is around 40–45% of default vLLM, while
batch-32 throughput remains only around 4–6%. This identifies the remaining matrix-compute gap without selecting
a favorable model or presenting a fixture as a trained benchmark.

Synthetic sweeps span widths 768/1024/2048/4096. Smaller subtrees help both architectures. Split-K and transposed
matrix-tile prototypes include slower configurations; they were not selected. Native FTZ primitive study checks
3,139,288 finite input pairs on local 5070 Ti and Thao 3060: add has no observed differences, but multiplication has
17 underflow-rounding differences on each. Unrestricted native FTZ multiply was rejected. `fast-linear-*` is an
unadmitted common-range prototype; its sweep baseline is patched too, so only its sampled CPU columns are an
independent oracle. It does not establish unrestricted reference equivalence. All associated scripts are retained.

Setup failures remain visible: the first activity reader used an unavailable `FunctionEvent.duration`; the first
decode kernel omitted an error-report helper; release initially cleared an inference tensor outside InferenceMode;
the first selector test incorrectly applied penalty at exact 1; and the remote benchmark bundle first omitted the
separate prompt-definition script. Corrected receipts use fresh names. No existing environment/driver was changed.

## What this does NOT show

- No universal heterogeneous or native Windows qualification, managed strict activation or M0–M6 completion.
- Synthetic projection or randomly initialized graph measurements do not establish trained-model quality.
- A speed target is a research objective, not an achieved result. Arithmetic may not be relaxed to reach it.
- No inference benchmark establishes distributed ES lifecycle, crash recovery or end-to-end learning acceptance.
