# DeepSeek Flash handoff and later Codex audit

Owner instruction, 2026-10-25: try DeepSeek v4.1 Flash in a separate branch/worktree; Codex will audit and
continue after usage resets. This document prepares that workflow; it does not start or configure DeepSeek.
The approved full M0–M6 objective remains incomplete and unchanged.

## Branch and baseline

- Work only in `/home/pc5070ti/projects/heteroes-deepseek-flash` on
  `work/deepseek-v4-1-flash-2026-10-25`.
- Implementation baseline: `253ebb98b490fc5ccc390436caf22d6a7c33123c`. The branch also includes this handoff.
- The Codex worktree `/home/pc5070ti/projects/heteroes` and its
  `fix/human-review-single-model-2026-10-24` branch are reserved for later review. Do not edit, checkout,
  reset or clean that worktree. Do not reuse the other audit/recovery worktrees.
- Commit logical changes on the DeepSeek branch. No push, merge, deployment, live device-state change or learning run.
  Do not merge or cherry-pick the trial automatically. A later Codex audit must inspect its actual diff and receipts.
- Read `AGENTS.md`, `docs/HANDOFF.md`, this document, the approved plan, numerical contract and ADR-012 before coding.
  Older handoffs contain superseded timings and acceptance counts.

## Verified starting state

The selected numerical implementation remains `3fd704a5`; `ced64601` records its acceptance. It uses a separately
versioned integer B14/B22 reference, exact live-FP16 weight conversion, shared/prepacked activations, bounded
split-K and exact attention subtrees. It is different arithmetic from the historical FP32 tree. The current
recipe/default is unchanged; every backend remains experimental and `hardwareQualified: false`.

Selected-source acceptance: 452 GPU tests per device on local/Nhut 5070 Ti, Quang 3060 WSL2 and Thao 3060 native
Windows; check-all, six tree/error mutants and Linux packages pass. Three trained models match across 5070 Ti/3060
for the recorded parent/canonical±/restore cases. Native Windows trained/installer and managed ownership/qualification
remain open. These finite receipts do not establish universal quality or completion of M1/M2/M0–M6.

At B32, local B22 reaches SmolLM2/TinyLlama/Qwen about 3861/1805/3471 output tokens/s, 23–27% of the prior vLLM
default measurements. Projection accounts for 66–84% of the measured B32 CUDA event sum. See
[the current source/timing comparison](strict-vllm-comparison-2026-10-25.md).

`253ebb98` adds 24 SIMT alignment/tail/split oracle cases and records two unselected vector-read experiments.
SIMT improves local B1 but regresses 3060 B1; MMA reads improve some cases but regress TinyLlama/3060 by about 4%.
Both retain parent token/logit equality across GPUs, but neither is selected. Preserve the unfavorable results.
Do not rerun immutable receipts under their old names or infer a generic gain from a favorable model/device.

## First implementation task

Continue general strict performance, with M6 feasibility as the next structural experiment: one primary frozen
int8 base, B22 activations and FP16 LoRA adapters. No M6 code was written before this handoff; only the existing
modules and design were inspected. This is a candidate format, not an accepted backend or a completed milestone.

1. Write independent oracle/boundary tests first. Specify the quantizer, packed row layout, scales, rounding,
   zero/subnormal/overflow behavior and artifact identity. A symmetric row-int8 format with stored FP32 scales
   is a starting candidate; pin one artifact instead of independently quantizing on each GPU.
2. Implement typed base storage and a separately named reference/CUDA operator. The existing B22 path uses
   three limbs for both operands, hence nine limb products; a frozen int8 operand could reduce that to three
   and remove repeated weight conversion/packing. This is a work-count hypothesis, not a throughput promise.
3. Beware final encoding: an exact int64 dot multiplied by a 24-bit FP32 scale significand can exceed int64.
   Premature FP32 conversion can double-round, underflow or overflow even when the final scaled value is finite.
   Prove and test the chosen integer encoding; do not substitute approximate float math under the old identity.
4. Base storage must be buffers/artifacts, with only floating adapters in the trainable schema. Do not fake an
   FP16 `.weight` by materializing a full dequantized matrix. Bound tiles, input packing, partials and cache.
   Preserve tied storage. Adapter perturb/update/replay/restore must use the unchanged canonical machinery.
5. Integrate with the restricted shared graph only after the operator/reference passes. Measure trained quality,
   tokens/rewards, lifecycle peaks and throughput on SmolLM2, TinyLlama and Qwen, on both GPU architectures.
   Explicitly label quantized-base/LoRA results; they do not replace full-weight FP16 ES results.

Relevant code: `runtime/src/heteroes/eval/{integer_reference,integer_cuda,integer_plan,integer_decoder}.py`,
`strict_decoder{,_packed,_graph}.py`, `reference_ops.py`, and `runtime/src/heteroes/model/{lora,schema}.py`.
The existing graph validator and LoRA loader require FP16 base parameters: do not bypass their guards silently.
Keep family-independent dimension/hardware rules; no model-name branches or Qwen-only claims.

M2 D10/D11 recovery/watchdogs, M3 storage/replacement, M4 lifecycle/qualification, M5 full acceptance and the rest
of M6 remain required. The plan's SHA-256 must stay
`4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.
Frozen noise/ES/ledger/generation-record behavior must not change.

## Environment and verification

- Local GPU Python: `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python`.
- CPU tooling: `.venv-backend/bin/python` and `.venv-backend/bin/ruff`. The worktree links the existing
  `.venv-backend` and `node_modules` for reuse; treat them as shared read-only dependencies, without installs/removals.
- Own scratch space is `.scratch/` in the DeepSeek worktree. Only the three model directories are linked to
  the existing local assets at `.scratch/strict-integer-20261025/models/{smol,tiny,qwen}`. Do not modify those
  assets or link/reuse the entire Codex scratch directory. Root disk had about 18 GiB free at handoff; avoid model copies.
- Existing pinned vLLM source can be read at
  `/home/pc5070ti/projects/heteroes/.scratch/vllm-source-20261025`, commit
  `e7473bf6862289f0647d1f4b01498288b181e063`. Do not update that shared clone.
- Owner GPU/SSH authorization covers all four machines for this task; it does not change lab approval/contribution.
  Use `HETEROES_GPU_ACCEPTANCE=1` and `--gpu` where supported. Existing remote helper source is recorded in the
  dated evidence folders; create fresh remote stages and output names. Never store credentials. Keep `ai`,
  `/mnt/sekai`, Archive disks and the deployed lab unchanged.
- CPU checks use `CUDA_VISIBLE_DEVICES=''` and worktree-local `PYTHONPATH=runtime/src`.
- Run meaningful targeted tests and `scripts/mutation-check.py` on scratch copies; then required check-all and
  packaging checks for the actual selected source. See `AGENTS.md` for commands. Do not run overlapping timed GPU probes.
- Evidence is append-only under a fresh dated folder with a README containing **What this does NOT show**.
  Preserve failed controls and counterexamples. Do not format generated files, fixtures or existing receipts.

Leave `docs/deepseek-flash-progress-2026-10-25.md` with exact commits, changed behavior, commands/results, remaining
gates and any live process/session handles. Distinguish proposed, implemented, tested and selected. Do not mark
the full objective or a milestone complete from operator tests alone.

## Resume audit after usage resets

Start by reading the actual branch/worktree status and progress note, then review:

```bash
git worktree list
git log --oneline 253ebb98..work/deepseek-v4-1-flash-2026-10-25
git diff --stat 253ebb98..work/deepseek-v4-1-flash-2026-10-25
git diff 253ebb98..work/deepseek-v4-1-flash-2026-10-25 -- runtime/src runtime/tests scripts
```

Inspect uncommitted changes as well as commits. Confirm unchanged plan/frozen contracts and no hidden weight
shadow or fallback. Audit test oracles and range/rounding arguments before executing candidate code. Reproduce
meaningful tests/mutations, trained cross-GPU candidate/restore and resource/performance claims at the reviewed
commit, with fresh receipts. Treat missing evidence as incomplete. Then fix and continue the approved M0–M6 work;
do not silently accept a smaller objective or merge the trial because its tests are green.
