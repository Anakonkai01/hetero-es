# Strict overnight continuation — 2026-10-25

Core commit **`e05c9ab5`**, after clean `81110a14`, on `fix/human-review-single-model-2026-10-24`.
The following documentation commit updates the current handoff. The user's autonomous full M0–M6 goal remains
active; this is a checked implementation checkpoint, not completion or a request to stop.

## Direction and scope

The owner requested unattended overnight continuation of the **full approved plan**, with the highest priority on
approaching vLLM performance across models and GPUs. GPU/SSH permission for local/Nhut 5070 Ti and Thao/Quang 3060
was explicitly renewed in this conversation. No sudo was needed; no credential is recorded.
Keep **no push, merge or deploy**, no device approval/contribution changes and no learning runs to demonstrate ES.

Read `AGENTS.md`, `HANDOFF.md`, [the approved plan](PLAN-SUA-HUMAN-REVIEW.md),
[decoder contract](../runtime/docs/strict-decoder-v1.md), [evidence](evidence/2026-10-25-strict-overnight/README.md),
[vLLM review](STRICT-PERFORMANCE-VLLM.md) and the unimplemented
[integer projection proposal](strict-integer-projection-design.md).
The plan is an exact byte snapshot of the previously external approved file, with a hash receipt; its scope is unchanged.

## Implemented and checked

- CUDA kernel v3 chooses independent per-thread/row subtrees by dimensions, including a faster one-row decomposition.
  The FP32 adjacent-pair tree, explicit rounding and integer signed-zero FTZ remain unchanged. No native FTZ multiply
  was adopted: a 3,139,288-pair study produced 17 underflow-rounding counterexamples on each tested architecture.
- Bounded stable original-owner KV slots and one retained decode CUDA Graph, shared by the existing restricted
  Qwen2/Llama/Mistral adapters. Packed prefill feeds the slots without a per-sequence model or weight copy.
  EOS compacts query owners while retaining their physical KV slot. Errors are checked before publishing IDs.
- Warmup restores selector state; live in-place weight mutations stay visible; parameter rebinding, stream/capacity
  changes and errors invalidate capture. KV/seen state clears at request boundaries. Explicit release clears buffers
  on their original stream before freeing capture. Reentry is refused. Noncached generation uses the old strict path.
- Additional tensor-payload admission covers actual prefill scratch, KV, decode/warmup storage and a margin.
  This does not impose a total-device budget or solve managed cross-process GPU ownership.
- Benchmark `--engine strict-graph` and `--graph-max-bytes`; full source/package fingerprints and intermediate
  failures/slower prototypes are preserved. Managed strict/default activation stays **off**, qualification **false**.

Verification on final code:

- `check-all-02.log`: **ALL PASS**, runtime **2,961 passed / 233 skipped**, backend **452 passed**, existing warning.
  Source-package imports, Python/JS formatting/lint, types/i18n, browser and Electron fixtures pass.
- **255 tests on each of four GPUs**. Four small graph layouts/two finite weight states agree across all four,
  including CPU/captured logits/tokens and exact fixture restore. Each target records **30 audited builds** with
  PTX/SASS available and zero violations. Post-decode KV ownership also has direct CPU-oracle tests.
- Final scratch mutation groups: CPU **3/3**, GPU **10/10**. Red stream, inference-tensor release, budget and
  publication regressions are retained. Fresh Linux source-copy package/import checks pass; four changed runtime
  modules match packaged bytes. Protected numerical directories/generation record remain unchanged.

## What performance now shows

Controlled parent inference: eight fixed prompts per checkpoint, FP16 storage, 32 greedy generated tokens,
EOS stopping/prefix reuse off, one excluded warmup and median of three synchronized host-wall repeats.
Batch 32 repeats those eight prompts four times. Separate library builds and unisolated hardware remain limitations.

| Local 5070 Ti, total tokens/s | Batch 1 | Batch 8 | Batch 32 |
| --- | ---: | ---: | ---: |
| Qwen2.5-0.5B graph strict | 209.9 | 422.6 | 500.7 |
| Qwen vLLM default (prior stage) | 518.7 | 4037.9 | 13802.5 |
| Qwen vLLM batch-invariant (prior stage) | 146.0 | 1164.5 | 4697.2 |
| SmolLM2-360M graph strict | 239.9 | 598.1 | 804.9 |
| SmolLM2 vLLM default | 529.2 | 4093.2 | 14429.4 |
| SmolLM2 vLLM batch-invariant | 173.8 | 1371.2 | 5339.8 |
| TinyLlama-1.1B graph strict | 133.3 | 255.3 | 288.8 |
| TinyLlama vLLM default | 322.9 | 2330.6 | 7791.8 |
| TinyLlama vLLM batch-invariant | 103.2 | 825.3 | 3194.7 |

Thao 3060 graph strict: Qwen **113.0/150.6/157.7**; SmolLM2 **131.1/194.2/211.6** at batch 1/8/32.
Parent tokens match across the two architectures on those two checkpoints. TinyLlama is local only so far.
SmolLM local input contains one HF download-tree metadata JSON absent remotely; the comparison explicitly checks
identical inference assets and records this difference, not equal full registration manifests or qualification.

Single-request throughput is now ~40–45% of default vLLM across three trained checkpoints; batch 32 remains ~4–6%.
One-layer layout profiles attribute ~93–99% of CUDA activity at batch 32 to projections. The current graph path has
helped launch overhead; another orchestration-only change is not justified as the main answer to the remaining gap.
No performance threshold or trained Mistral/native Windows/managed-lifecycle acceptance is claimed.

## Continue with the real remaining work

1. **Matrix compute is still first priority.** Evaluate a separately versioned row-scaled integer reference/kernel,
   starting with the proposal's two-limb case and independent CPU boundary/rounding/overflow tests. Integer Tensor
   Core accumulation needs a nonoverflow proof, bit-exact reconstruction, generated instruction/resource audits and
   cross-GPU answers. Never replace current tree arithmetic under its old identity or equate quantization with proof.
   Actual throughput must justify full decoder integration; accuracy, parent/canonical-perturbation sensitivity,
   exact restore and multi-model/GPU gates remain mandatory. Evaluate compiler/dependency choices against native
   Windows from the start; a Linux-only feasibility result cannot close M4.
2. Extend trained checkpoint/candidate coverage using the pinned new local models. Prepare asset-only input
   directories for future managed comparisons, preserving original receipts/manifests; do not change historical
   registration identities just to drop HF download metadata. No full FP32/quantized weight shadow on GPU.
3. Keep M0–M6 intact: M2 audit projection/API/UI, progress watchdog/hard caps and persisted D10; M3 streaming,
   backoff/verify/retention dependencies and audit-sidecar/replacement consistency; M4 qualification, one managed
   weight set across roles/processes, SDK/API/export and native packaging; M5 system acceptance; M6 one frozen-base
   quantization format plus LoRA without a full dequantized shadow. None is closed by these inference measurements.

## Reproduction and operations

- Python local: `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python`; vLLM isolated env remains
  `.scratch/vllm-venv-20261024/bin/python`. Existing `ai`/worker environments are unchanged.
- New trained models under `.scratch/strict-models-20261025/`, revisions/files in `trained-model-downloads-01.json`:
  SmolLM2 `a10cc1512eabd3dde888204e902eca88bddb4951`; TinyLlama `fe8a4ea1ffedaf415f4da2f062534de366a451e6`.
  Only safe data/tokenizer files were downloaded, no remote code or pickle. Both larger layouts used an explicit
  4 GiB graph admission budget. The local disk has about 24 GiB free after downloads; do not use Archive or `/mnt/sekai`.
- Final remote source/tests: `/tmp/heteroes-strict-overnight-20261025-03` on all three SSH hosts. Earlier `-01/-02`
  retain prototype/stage data. The benchmark additionally needs `scripts/probe_strict_backend.py` for prompt constants;
  the missing-file failure on Thao was corrected by copying that script. Include it in any new benchmark bundle.
- Thao SmolLM assets: `/home/thao_nguyen/.cache/heteroes-strict-models-20261025/SmolLM2-360M-Instruct/<revision>`.
  Large model files were copied to its disk-backed home, not its tmpfs `/tmp`.
- GPU opt-ins and process-local WSL driver-library selection remain as in the previous handoff. All owned check,
  mutation, probe, download, package and benchmark chains returned terminal status at this checkpoint.
  Read-only deployed receipt: `82c37fca`, three services stopped. No lab state, driver, approval or contribution changed.
