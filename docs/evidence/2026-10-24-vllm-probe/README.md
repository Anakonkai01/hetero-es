# vLLM vs strict backend: cross-GPU token equality (2026-10-24)

Question from the owner: can vLLM replace the strict backend? This folder answers only the token-equality and
speed part, on the pinned Qwen2.5-0.5B-Instruct (`7ae55760...`), FP16 weights, greedy decoding.

- vLLM 0.32.0 (torch 2.13.0+cu130) in isolated environments: local `.scratch/vllm-venv-20261024`, Thao
  `~/heteroes-vllm-20261024`. Existing envs, workers and lab untouched. `VLLM_USE_FLASHINFER_SAMPLER=0` because
  FlashInfer's JIT sampler needs `nvcc`, which neither machine has (`vllm-nhan-*-01.json` record that failure).
- Script: `runtime/scripts/probe_vllm_tokens.py`. Prompts: the 8 fixed strict-probe prompts plus 200
  deterministic templated word problems (`generated_prompts` in `probe_strict_backend.py`), the same token ids,
  max 256 new tokens. Modes: default and `VLLM_BATCH_INVARIANT=1`.
- Strict backend on the same 208 prompts: `strict-{nhan,thao}-large-01.json` (`probe_strict_backend.py
  --candidates 0 --generated 200 --max-new-tokens 256`).
- Machines: nhan (RTX 5070 Ti, sm_120, Linux) and thao (RTX 3060, sm_86, WSL2).
- `summarize.py` writes `summary.json` (input hashes included); its output is in `summarize-01.log`.

## Result (`summary.json`)

| Path | 5070 Ti vs 3060, 208 prompts | Same machine: batch of 128 vs one at a time | Throughput, batch of 128 (nhan / thao) | One sequence (nhan / thao) |
| --- | --- | --- | --- | --- |
| vLLM default | 15 prompts differ (first differing token at positions 2–241) | differs | 33,904 / 11,182 tok/s | 522 / 236 tok/s |
| vLLM batch-invariant | **15 prompts differ** (positions 73–241, one at 2) | equal | 14,722 / 7,589 tok/s | 146 / 78 tok/s |
| Strict CUDA kernels | **0 differ** (47,826 tokens) | row-independent by construction and test | not implemented | 65.8 / 24.8 tok/s |

The small first run (8 prompts × 64 tokens, `vllm-*-02.json`/`vllm-thao-*-01.json`) showed batch-invariant
vLLM equal on both GPUs. The larger run disproves that impression: batch invariance holds on one machine,
but not between architectures. Strict and vLLM tokens differ from each other on all 208 prompts (median first
difference at token 8). That is expected and allowed: they use different arithmetic (ADR-012/D4).

## Reading for the owner's decision

vLLM cannot be the strict path: heterogeneous GPUs (D2/D3) produced different texts for 7 % of prompts even in
its deterministic mode. Its batching is 100–300× faster in aggregate than the strict backend's current
one-sequence decode, so its techniques (continuous batching, paged KV cache, CUDA graphs) are the model for
strict-backend throughput work. Other blockers were not tested here and are design facts: ES in-place perturb and
exact restore, D1 one weight set per GPU (vLLM reserves a VRAM fraction and keeps its own weights), native Windows.

## What this does NOT show

- Two GPUs, one model, parent weights only (no perturbed candidates), one vLLM version, greedy decoding.
  Other vLLM versions/backends/options may differ more or less. Zero strict differences on 208 prompts is a finite
  result, not a proof for every input.
- Throughput numbers are host wall times on unisolated machines and different workloads: vLLM batched 128
  sequences from the 8 fixed prompts; strict ran one sequence at a time. They are not a like-for-like efficiency
  comparison or a quality comparison.
- No native Windows, no vLLM weight-update/restore experiment, no memory measurement for vLLM.
