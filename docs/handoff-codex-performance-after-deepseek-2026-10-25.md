# Next Codex session: audit and continue measured strict performance

Owner's final instruction for this session: stop implementation now; **Codex will audit and continue next session**.
Corrected DeepSeek checkpoint: `777a0211`; performance code `f9bfd254`; receipts `c5d50ecb`.
This replaces the previous next-task assignment to DeepSeek and the old `6299f62e` starting state. Do not restart
the artifact implementation or blindly repeat fixes already reported in `cc76a03d`. The full approved M0–M6
objective remains unchanged. The closing session only prepares this handoff; it starts no numerical work,
benchmark, deployment or integration.

## 1. Goal, branch and starting evidence

The primary goal remains general strict-kernel performance approaching vLLM across models and GPUs, while
preserving the declared arithmetic, meaningful correctness/restore tests and one primary GPU weight set.
The next deliverable is further implementation plus measured cross-architecture evidence, not another format-only milestone.

- Source worktree: `/home/pc5070ti/projects/heteroes-deepseek-flash`, branch
  `work/deepseek-v4-1-flash-2026-10-25`. It was clean at `777a0211` before documentation-only handoff updates.
- Begin next session by reading actual worktree/branch status. Work in a separate Codex branch based on this
  trial checkpoint, without merging it into the original Codex branch or modifying DeepSeek's worktree.
  A proposed branch name is `work/codex-frozen-perf-2026-10-25`; create/reuse a suitable clean owned worktree.
  Do not reset an existing branch or overwrite WIP. An earlier Codex audit worktree may still be at `6299f62e`;
  do not accidentally benchmark that stale source. The original Codex worktree retains the B22 baseline.
- Read `AGENTS.md`, `docs/HANDOFF.md`, this handoff, the progress note and the approved plan/ADR-012.
  Use current Git status and source as authority; a later documentation commit may advance HEAD without changing kernels.
- `cc76a03d`: reported RNE-midpoint, artifact-seal, strict-adapter and defined-limb-arithmetic fixes.
- `f9bfd254`: first rank product uses `row_tile=1`; fused `strict_lora_finish` implements the second product,
  strict scale, zero-delta select and strict add without changing the declared arithmetic.
- `c5d50ecb`: `docs/evidence/2026-10-25-frozen-audit-perf/`, including raw durations, model manifests,
  profile, test/mutation logs, harness source and limitations. `777a0211` updates the progress/handoff.

A limited documentation check verified all 28 entries in that folder's `SHA256SUMS` and recomputed the reported
Smol/Qwen ratios from raw five-observation medians. That is not an independent numerical, GPU or lifecycle audit.
Do not treat the receipt's `equal=true`, a source checksum or a clean tree as full acceptance.

## 2. Preserve what was achieved, and state its scope accurately

Local Linux 5070 Ti, rank 8/alpha 16, greedy 32 output tokens, context 512, fixed eight-prompt pool,
one warmup and five timed observations. Total output tokens/s:

| Model / supported variant      |   M6 B32 before | M6 B32 after |            Gain | New B8 | Prior vLLM B32 ratio |
| ------------------------------ | --------------: | -----------: | --------------: | -----: | -------------------: |
| SmolLM2-360M, frozen head      |          2511.8 |       3077.7 |          +22.5% | 1101.4 |                21.3% |
| Qwen2.5-0.5B, frozen head      |          2413.2 |       2907.5 |          +20.5% | 1215.8 |                21.1% |
| TinyLlama-1.1B, frozen no head | unmeasured here |       1437.3 | not established |  785.9 |                18.4% |

Smol/Qwen B8 gains are +24.0%/+24.8%; B1 is unchanged inside observed variation. A fixed random nonzero-B fill
reproduces the throughput within about 0.2%. This exercises the add path; it is neither a trained adapter nor a
canonical ES perturbation, and it does not establish quality or cross-GPU equality.

The gain is relative to the preceding **M6 frozen-base/LoRA path**, not proof of an improvement over the older
full-weight B22 path. Tiny's recorded B22 B32 is 1810.5 vs frozen 1437.3, about 20.6% slower in this harness.
Smol/Qwen are also below earlier separate-stage B22 observations of 3861.3/3470.5. Refresh matched B22 controls
before a general comparison. Model/search-space changes and adapter overhead must remain explicit.

The vLLM ratios use old, separate-stage default controls: 14429.4/13802.5/7791.8 tok/s for Smol/Qwen/Tiny.
They are orientation data, not fresh matched comparisons. Near-vLLM performance is not achieved.

Reported checks: runtime CPU 3131 pass/444 skip; GPU 180 pass; finish mutations 3/3 killed. The GPU command covers
`test_strict_cuda.py` and `test_frozen_int8_decoder_cuda.py`; it is not a receipt for every GPU test on every host.
The three mutants target the fused finish, not every M6 invariant. Preserve the exact test/commit scope.

## 3. Correct the interpretation of the profile

The Smol B32 frozen-head profile contains:

| Kernel               | Self CUDA share | Meaning                                                          |
| -------------------- | --------------: | ---------------------------------------------------------------- |
| `frozen_linear`      |           32.4% | integer base MMA work                                            |
| `strict_lora_finish` |           26.1% | second adapter product and fused epilogue                        |
| `strict_linear`      |           13.1% | strict floating projection work; attribute individual call sites |
| `strict_attention`   |           12.7% | attention                                                        |
| `frozen_finish`      |            5.0% | split partial finish/encoding                                    |
| `integer_input`      |            3.3% | activation quantization/packing                                  |

**71.5% is the sum of three projection categories, not base-only time.** Base and adapter projection work both
remain candidates. Do not attribute all `strict_linear` calls without checking their call sites. The profile is
one Smol/5070 Ti case with zero B; it does not characterize Tiny, Qwen, B1 or 3060. It also uses a slightly shorter
sixth prompt than the benchmark. The next profile must consume the exact benchmark token IDs/configuration.
CUDA event sums are not host wall shares and do not directly predict end-to-end speedup.

## 4. Next work, in order

### A. Pin the actual workload and artifacts, then verify the fixed gates

1. Inventory the current tree, commits and any live jobs. Do not reset/clean/stash someone else's changes.
   Keep the existing source and unfavorable receipts. New stages/output paths must be fresh.
2. Create a pinned on-disk frozen artifact bundle and adapter file for the measured model configuration.
   Record parent file manifests, quantizer/layout/scales, per-module and bundle hashes, adapter bytes/schema/hash,
   rank, alpha/scaling bits, targets and head variant. The current receipts pin source/seed but not adapter bytes
   or a full on-disk frozen bundle. Generate once, then use identical artifacts on both architectures.
3. Preserve separate states: original zero-B adapter, the fixed nonzero-B throughput probe, and canonical nonzero
   plus/minus ES adapter candidates. Do not independently initialize/requantize on each GPU and call it identity.
4. Verify the `cc76a03d` fixes against independent tests of the current source: RNE below/at/above the overflow
   midpoint, min-normal/signed FTZ, artifact mutation/forgery/admission, strict nonzero adapter products/scale/add,
   defined negative-limb reconstruction and exact restore. Reopen a fix only if current evidence fails.
5. Check fused-rank admission against the implemented rank <= 32 limit. Unsupported configurations must fail
   explicitly before execution, without an ordinary-vendor fallback. Retain a valid strict reference path.
6. Extend the harness to save full generated token streams or canonical full-stream hashes with counts, plus
   reward/text and optional logit hashes needed for comparisons. A short token sample and within-run `equal=true`
   cannot prove pre/post or cross-GPU regeneration. Refuse an existing output path before loading/launching.

### B. Establish strict equality on SM86 and SM120

Use the same pinned base, adapters, schema, prompts, decode configuration and candidate descriptors on local
5070 Ti and at least one 3060. Record driver/Torch/CUDA/NVRTC/OS and code/build identities separately from
portable identity. Keep explicit GPU opt-ins; the owner's authorization already covers these hosts.

- First test operators and decoder fixtures: odd dimensions/tails/offsets, ranks, cancellation, exponent endpoints,
  zero/subnormals, RNE/FTZ/overflow, nonfinite failures and captured replay.
- Then compare the three real models for original and nonzero parent adapters, canonical plus/minus candidates
  and restored parent. Exercise batching, row permutation, packed prefill, cached/uncached decode and stopping.
- Required system outputs are identical token IDs/text/reward under the same identity; record stronger bit-level
  operator/logit evidence where claimed. Check exact adapter restore and unchanged frozen artifacts.
- Compare unfused `cc76a03d` and fused `f9bfd254` with identical pinned bytes for a finite end-to-end corpus;
  different source fingerprints do not permit a scheduling-only optimization to change arithmetic.
- A mismatch is evidence to preserve and fix. Do not choose one GPU as correct by assumption, switch to FP16,
  drop the failing model/candidate, or coerce infrastructure failure into reward zero.

Do not claim heterogeneous strictness from the local 180-pass receipt. Package/native claims need their own
actual-source acceptance after the final implementation is selected.

### C. Run matched throughput controls on both architectures

Measure **all three models x B1/B8/B32 x 5070 Ti/3060**, with explicit supported variants. Include:

- current frozen-base/strict-LoRA path;
- its preceding M6 control for the claimed gain;
- the B22 path as a separate model/search-space baseline;
- vLLM default on the same host/workload; batch-invariant results are a separate optional control;
- the ordinary FP16 experimental decoder only as a clearly labelled non-strict baseline.

Use exact shared token IDs, greedy 32 output tokens, context 512, EOS stopping and prefix reuse off. B1 uses
prompt 0, B8 each prompt once and B32 four repeats. Record cold load/prepare/compile/capture separately from
warmed synchronized host wall time, at least one warmup and five timed observations, raw durations, median/spread,
allocator and process memory. Preserve all cases, including B1 regressions and unchanged/noisy results.

Prefer paired ABBA for variants sharing one primary model/contract. For different representations use sequential
loads/processes without retaining a second complete GPU model. Do not overlap timed probes on the same GPU.
Pin engine/runtime versions and graph/admission/memory settings; a different CUDA build is a recorded limitation,
not evidence of identical numerical work. Install optional tools only into an isolated owned environment, never `ai`
or shared dependencies. If a vLLM control cannot run, retain the failure and mark it unavailable; do not rename an
FP16 baseline as vLLM or substitute a different prompt/budget.

Tiny's frozen-head variant is currently unsupported because its head is untied. Keep that row unavailable;
do not silently replace its number with B22 or the no-head variant under the same label. Aggregate only comparable
cases with explicit coverage, keeping Tiny visible. No model-name-specific dispatch or favorable-case selection.

The old README reproduction commands reuse immutable output names and a scratch namespace. Do not execute them
literally: create fresh versioned paths/stages, and avoid deleting or overwriting existing outputs.

### D. Implement the next profile-backed projection optimization

With the matched baseline established, profile the actual workload on each architecture and representative
models/batches. Separate base MMA, split finish/96-bit encoding, input packing, both adapter products, attention,
launch/capture and host costs. Reuse the benchmark's tokenized workload instead of maintaining a second prompt list.

Choose a concrete bottleneck hypothesis, write a discriminating test, implement in scratch, compare, then retain
or reject with evidence. Candidates include base weight loads/layout, tile reuse, register pressure/occupancy,
exact integer split-K, skinny-rank scheduling, grouped projections and legal fusion. Safe bounded integer sums may
change partition without changing value; strict floating trees and contraction rules must remain as specified.
The current 9-to-3 limb reduction alone is not a throughput promise.

If Tiny's profile shows the untied FP16 head dominates, consider a proper typed **primary** int8 untied-head path
with CPU/CUDA reference, explicit identity and no retained full FP16 head shadow. Dispatch by capability/dimensions,
not model name. For the existing tied-head sidecar, keep storage tie distinct from numerical equality: the int8
head approximates the FP16 embedding and must remain explicitly identified and quality-tested.

Retain the strict arithmetic of `f9bfd254` for scheduling/layout/fusion comparisons. A different precision,
quantization or adapter arithmetic needs a new reference/identity and its own quality/equality gates; it cannot
be silently counted as a same-contract speedup. Keep the historical FP32 and live-FP16 B22 paths intact.

### E. Complete quality and lifecycle evidence without a learning run

Evaluate quantized-base quality separately from cross-GPU correctness. Pin a finite corpus/scorer and record
its token IDs/hash, loss or other justified metrics, token/text/reward differences and limits against the original
base. Test the nonzero canonical candidates, not just zero B or a random normal fill.

If an already trained compatible adapter is available, pin and evaluate that artifact too. If none is available,
state that trained-adapter quality is missing and continue safe kernel/equality work. **Do not start training or
an ES learning run to manufacture this gate:** the owner has not authorized learning. A finite canonical
perturb/update/replay/restore primitive check is allowed; it does not establish learning or trained quality.

Measure load/prepare, candidate entry, perturb, inference, restore and export/reload: host RSS, GPU allocated/
reserved peaks and actual weight ownership. Current peak-memory receipts are cumulative allocator peaks,
not complete lifecycle/process acceptance. Keep one primary full inference weight set across roles and reloads;
release the previous GPU model before independent reload. Bound scratch/KV and reject stale/mutated bindings.

## 5. Verification and evidence discipline

- Tests precede new behavior. Use independent rational/known-answer oracles and scratch mutations; a surviving
  mutant needs a discriminating test or documented equivalence. Cover the behavior actually changed.
- Runtime CPU tests need the numerical Python with `CUDA_VISIBLE_DEVICES=''`, not the backend-only venv without Torch.
  GPU tests use `HETEROES_GPU_ACCEPTANCE=1` and `--gpu` where supported.
- Local numerical Python: `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python`; use worktree-local
  `PYTHONPATH=runtime/src`. Reuse read-only shared models/dependencies; do not duplicate/download them unnecessarily.
- Finish appropriate targeted controls before timing. Run required runtime/backend/check-all and fresh Linux
  packaging for the final selected source. Complete other GPU/native acceptance at the scope claimed; a Linux
  wheel or native fixture does not establish native trained/installer/managed qualification.
- Record the actual commit and all relevant source hashes, artifact/schema/adapter/prompt identities, commands,
  raw timings/outputs, failures, rejected variants, memory, PTX/SASS audit availability and build identities.
  Archive text audits for the actual fused kernel instead of assuming the ordinary compile path is sufficient evidence.
- Evidence is append-only in fresh dated folders with **What this does NOT show**. Do not format or overwrite
  fixtures, generated files or existing receipts. Do not use the old output names even for a reproduction.
- Inspect staged changes; commit logical groups on the chosen Codex continuation branch, preserving unrelated
  WIP and other worktrees. No push, merge, automatic cherry-pick, deploy or live device approval/contribution change.
- Keep credentials, `ai`, shared dependencies/model assets, `/mnt/sekai`, Archive disks and the deployed lab unchanged.
  The initial handoff's environment and GPU/SSH permissions still apply; do not re-request the same permission.

## 6. Required handback

Update `docs/deepseek-flash-progress-2026-10-25.md` with exact commits and separate proposed/implemented/tested/
selected-in-trial/unaccepted states. The next handback must include:

1. Pinned frozen-base and adapter files/manifests and the exact code/config used on both architectures.
2. Operator and real-model cross-GPU parent/nonzero-candidate/restore results, including counterexamples and scope.
3. A full model/GPU/batch/variant table with matched baseline, new throughput, ratio, variation, memory and quality
   status. Distinguish the M6-to-M6 gain, M6-vs-B22 tradeoff and matched vLLM ratio.
4. The next implemented projection optimization and its profile-backed decision across models/GPUs, including regressions.
5. Quality/lifecycle/package/hardware gates still missing. If trained adapters are unavailable, keep that explicit.
6. Reproducible scripts/commands and any live job/session handles. Verify a specific job is live before waiting;
   an observation timeout is not terminal and does not justify restarting duplicate work.

Do not close a performance task merely because the format/tests pass, and do not call a noisy or regressed case
an improvement. Report the achieved vLLM ratio rather than changing the meaning of "near vLLM". A successful
local +22% does not finish M6 or the full plan; the remaining general-performance objective stays open.

`hardwareQualified` remains false. Fusion is selected only inside the experimental frozen decoder, not as a
managed recipe/default activation. M1/M2 remain incomplete; D10/D11 recovery/watchdogs, M3 storage/replacement,
M4 ownership/qualification/native delivery, M5 full-system acceptance and M6's full lifecycle remain required.
The owner asks Codex to continue **next session**, beginning with the actual-source audit and then the measured
performance work above. No additional DeepSeek implementation is requested by this closing handoff. No merge or
managed activation is authorized merely by resuming the work.

The approved plan must retain SHA-256
`4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.
Frozen noise/ES/ledger/generation-record behavior and historical identities remain unchanged.
