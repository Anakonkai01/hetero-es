# Claude handoff after Codex performance work — 2026-10-26

The owner explicitly ended this session and requested handoff to Claude because context/tokens were
running low. Stop auto-run; no new kernel/benchmark, push, merge or deployment is authorized by the
session-close request. Resume experiments only in the next owner-authorized session.

## Workspace and authoritative state

- Use `/home/pc5070ti/projects/heteroes-codex-frozen-perf`, branch
  `work/codex-frozen-perf-2026-10-25`. The local commit containing this handoff seals the final receipts.
  Receipt HEAD immediately before this closure was `01e13637`; inspect `git log` for the closure commit.
- **Selected runtime source is still `b1ef257a`: exact B22 raw FP16 prefetch2.** Subsequent changes
  are evidence/handoff records and unselected scratch experiments, not newly selected runtime code.
- Original `/home/pc5070ti/projects/heteroes` and `heteroes-deepseek-flash` were verified clean and
  untouched at closure. Check all worktrees before modifying anything; do not work in an old audit clone.
- Read `AGENTS.md`, `docs/HANDOFF.md`, `runtime/docs/numerical-contract.md`,
  `docs/PLAN-SUA-HUMAN-REVIEW.md` and relevant numerical ADRs. Approved plan hash remains
  `4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.
- All GPU jobs submitted by this session completed. No background experiment is pending. All final
  raw evidence is retained with SHA256 manifests; never rewrite sealed data or format raw failure logs.

## Owner objective and constraints

Finish own strict inference kernels approaching vLLM performance, then complete the full M0–M6
plan. The vLLM impact survey is already finished. A wrapper around vLLM does not satisfy the own-kernel
objective. The owner warned against tunneling into small operator tweaks and requested whole-path evidence.

- D1: one complete primary inference weight set per physical GPU across managed roles; no full
  FP32 or transformed quantized shadow. Bounded operator scratch and canonical CPU snapshots are allowed.
- D2/D3: same candidate/input must give the same tokens/rewards across heterogeneous supported GPUs.
  Finite passing samples do not prove an all-input guarantee; do not restrict workers to identical GPUs.
- D4: alternative arithmetic can have a new explicit backend/recipe identity. It need not match the
  old FP32 path. Historical noise/update/replay identities remain frozen.
- D5: full/subset ES with an FP16 model first, quantized frozen base plus LoRA next. Do not silently
  replace the primary objective with LoRA or full-weight ES on a quantized primary model.
- Keep native Windows support as a real direction. Native acceptance and WSL2 acceptance are distinct.
- No push/merge/deploy, live device-state changes, learning runs or changes to the Conda `ai` environment.
  Latest owner restrictions override broad older push permission in AGENTS.md. Do not use `/mnt/sekai`
  or the unverified/full Archive disk. Local root had about 13 GiB free at the last storage read.
- No subagents unless the owner or an applicable instruction explicitly requests delegation.

## What is actually selected

Read `docs/evidence/2026-10-26-strict-prefetch/README.md`, sealed in `c9a6cf55`.

| Model / GPU | B32 total token/s | Gain over immediately prior B22 |
| --- | ---: | ---: |
| Smol / 5070 Ti | 4504.4 | 10.76% |
| Qwen / 5070 Ti | 4346.3 | 15.83% |
| Tiny / 5070 Ti | 2321.8 | 16.86% |
| Smol / 3060 | 1567.2 | 8.18% |
| Qwen / 3060 | 1328.0 | 8.02% |
| Tiny / 3060 | 631.1 | 9.24% |

These are the short eight-prompt pool, 32 greedy outputs, context 512, ABBA ten-sample standalone
generation measurements. B1 has no general prefetch gain. Selected throughput is still only about
30–33% of prior vLLM controls; the performance goal is not complete.

Three trained models' parent/canonical seed7001 ±/restore hashes, logits, tokens/text/reward agree
between SM120/SM86 for the surveyed cases. Native Win11/3060: 505 tests plus small layouts and
trained Qwen canonical candidates match Linux/WSL2. Selected source full check ALL PASS: runtime
3158 passed/461 skipped, backend452; isolated Linux Worker/SDK141 runtime files and Server23 match.
This is not managed kernel activation, universal hardware qualification or full M0–M6 acceptance.

Earlier selected stages remain: `20856dea` frozen-LoRA subwarp improvements, `9acf8bfa` paired B22
reads, `3735d6db` live merged FP16 Parameter fix. The LoRA gains are separate from full-weight ES.

## Important new answer: the 7.4–7.8k GEMM path

The owner specifically asked why this faster path was not chosen. It is own graph plus vendor
`F.linear` FP16 projections (including the head), not vLLM, and retains one primary FP16 weight set.
The prior Qwen B32 controls are 7492 separate / 7804 merged token/s on short32; chat128 is about6243.

**It now has actual D2 counterexamples**, not merely a missing test. Read
`docs/evidence/2026-10-26-strict-fp16-parity/README.md` and `comparison-01.json`:

- Same Qwen assets/schema/candidate weight hashes/input IDs/backend source on both GPUs.
- First32 GSM8K chat prompts, parent/seed7001 ±, 128 outputs, EOS stopping, batch8/32.
- Default batch32: 33/96 token rows differ. FP32 accumulation policy (both FP16 precision flags
  disabled) still differs26/96. Batch8 differs14/96 under each policy.
- Parent `gsm8k-test-002` diverges at output index4 by default (106987 vs26242), or index7 under
  the FP32 accumulation policy (21322 vs99235). Restore is exact and same-host parent/restored
  inference matches. Batch-size changes also produce many differences on each host.
- All rewards are zero at B32 and only1/96 answers completes. Do not claim reward impact is small
  from this truncated set. D2's per-token requirement already rejects this configuration.
- Two comparer CPU tests pass and 2/2 mutants are killed. No new performance or native claim.

The vLLM survey is separate: `3ee55bbf`, `2026-10-26-vllm-impact/`. Chat512 first64 questions plus
eight canonical candidates has 7/576 cross-GPU reward flips, including completed answers. Do not
conflate those results with own FP16-GEMM results or infer learning impact. Native Windows upstream
vLLM support and heterogeneous reproducibility constraints were documented in that survey.

## Unselected research: do not repeat discarded branches blindly

- `4d488217`: contiguous integer projection grouping only~3% at B32; wider16-byte raw copy~4.7%
  SM120/~9.1% SM86. Not selected; lifecycle/three-model/candidate/native/mutation gates remain.
- `5bbaa110`: bounded FP16 integer MMA/half2/vendor-bmm variants have inconsistent operator gains;
  no accepted decoder/quality path. Shared-radix tiling and captured prefill provide no compelling
  end-to-end gain. Direct ordered FP32 FMA is slower in all five cases. Stop those implementations.
- `ef21c7c3`: detailed external-event attribution shows attention~2.8/7.9ms in final chat decode,
  but a warp-attention rewrite gives only~1% whole-generation benefit. Operator speedups did not
  transfer. Timing event nodes perturb scheduling; host `read` time includes GPU waiting.
- `01e13637`: exact own speculative decoder with prior completion proposals, no cross-candidate KV.
  On one Qwen chat prompt, seed7001 ± B1 gains~30%/~145%, but B8 remains3–5% slower even after stable
  dummy-prefix rows remove recapture. Six GPU tests each host, two CPU each, 3/3 mutants killed.
  This is conditional B1 research, not a general ES speedup or the B32 solution. Parent bank cost
  is excluded from warm speed ratios and explicitly recorded. Do not keep tuning it for the main goal.

## Last open prototype: B13 radix128/Karatsuba

Read `docs/evidence/2026-10-26-strict-karatsuba/README.md`. Scratch source is in
`.scratch/strict-karatsuba-20261026/`; final replayable copies are sealed under evidence `harness/`.

- New arithmetic: per-row power-of-two scale `2^(floor_log2(absmax)-12)`, RNE q in±8192;
  exact integer dot then existing FP32 scaled RNE/FTZ encoding and bias. It is not B22.
- q=low+128*high; low/high/sum fit signed bytes. Three products reconstruct as
  p0+128*(ps-p0-p2)+16384*p2. Own int8 MMA reads raw live FP16 weights; no persistent weight shadow.
- Final version packs only low/high input planes, adds packed signed bytes in registers and keeps
  weight operands intact across both M groups. The initial two-plane version mutated b operands
  for the second M group; the 19-row CPU oracle test caught it. Failed attempts are retained.
- Five local tests pass. Final five-shape ratios versus B22 are about1.05/1.19/1.19/1.33/1.31.
  Schoolbook four-product control with the same B13 arithmetic is about1.00/1.22/1.22/1.34/1.27.
  Three products do not consistently beat four; do not claim a whole-model gain.
- **No B13 decoder adapter has been written or run. No quality, canonical trained candidate,
  SM86/native, mutation or full-product acceptance exists for B13.** Last actual computation was
  the final five-shape operator pilot; all submitted jobs are terminal.

If continuing this finite direction, first decide whether the modest operator improvement warrants
new-arithmetic qualification. One discussed but unimplemented next step is B13 body plus unchanged
B22 LM head, CPU decoder oracle, then a trained whole-model pilot. Keep explicit identity/head
arithmetic and bounded request metadata; do not use an inherited B22 identity for B13 execution.
Stop if full-model gains or quality do not justify it. Do not spend many iterations merely chasing
the nominal MMA count. The owner wants meaningful whole-path progress and broader architectural thinking.

## Environments and resumption commands

Local matching Python: `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python`, Torch2.13.0+cu132,
Transformers5.17.0, RTX5070Ti SM120. Models are read-only at
`/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/{qwen,smol,tiny}`.
Use `CUDA_VISIBLE_DEVICES=''` for CPU checks and `HETEROES_GPU_ACCEPTANCE=1`, plus `--gpu` when
supported, for authorized GPU work. One timed inference job per physical GPU; native Windows and
WSL2 on Thao share the same3060. Poll a known live handle; never restart because observation timed out.

The approved plan authorizes standalone SSH to `thao_nguyen@100.92.20.58` with
`-F /home/pc5070ti/.ssh/config -o BatchMode=yes -o ConnectTimeout=8`. Matching remote Python:
`/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12`.
Process-local CUDA path, required to avoid the stale WSL JIT discovery crash:
`LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib`.
Do not change drivers or the global environment.

Remote selected runtime: `/tmp/heteroes-strict-prefetch-20261026-01/selected-02/src`, tests alongside;
pytest shim path `/tmp/heteroes-strict-integer-20261025-02/testdeps`. Model cache:
`/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models/`.
Last FP16 probe stage: `/tmp/heteroes-strict-fp16-parity-20261026-01/`. Speculative tests:
`/tmp/heteroes-strict-speculative-20261026-01/`.

Native Windows isolated environment already exists:
`C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01\venv\Scripts\python.exe`.
Its source/model setup and last native harnesses are recorded in the selected prefetch evidence;
do not infer that newer scratch experiments are native-qualified.

Before selecting runtime changes: meaningful tests first, independent arithmetic/whole-path gates,
scratch mutation checks, canonical parent/candidate/restore parity across architectures and native
direction, resource/lifecycle gates, then appropriate full checks and isolated packaging. Do not rerun
the entire product suite for an unselected scratch operator. Keep all failed receipts and their limits.
M0–M6, watchdog/D10, storage/replacement, managed ownership/activation and installer work remain open.
