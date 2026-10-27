# Claude handoff after Codex strict-performance research, 2026-10-27

## Start here

The owner explicitly stopped Codex and asked Claude to continue: **"thôi chốt phiên đi, để claude làm tiếp"**.
The Codex goal is **paused**, not complete. No GPU computation is running at handoff. Do not infer that
the 80% target was reached from the amount of research or the number of passing tests.

- Worktree: `/home/pc5070ti/projects/heteroes-codex-frozen-perf`.
- Branch: `work/codex-frozen-perf-2026-10-25`. Work is committed locally; no push/merge/deployment in this session.
- **Selected runtime: `0eb86cb948878fe430049882b80b3a5ad74730ba`.** Later commits record evidence/docs;
  runtime Python source is unchanged. Verify with `git diff 0eb86cb9 -- runtime/src`.
- Selected matched Qwen B32: **short32 9866.13 token/s**, **chat128 9889.77 token/s**. Short32 is
  **71.315%** of vLLM 13834.6. The primary goal remains near 80% on this same short32 control.
- Nhựt's spare 5070 Ti was confirmed idle and shut down at the owner's request. **Leave it off.**
  Local `pc5070ti` is Nhân's 5070 Ti. Thảo's 3060 has WSL2 and native Windows receipts.
- Owner gave full SSH and sudo authority in the conversation. Do not copy authentication material into
  the repository, command logs or this document. This authorization supersedes the older generic SSH
  request rule in AGENTS; it does not authorize changing lab device approval/contribution state.
- System disk has only about **5.7 GiB free / 99% used**. Avoid large archives/model copies. Never use `/mnt/sekai`.

## What is fully accepted

Read [combined acceptance](evidence/2026-10-27-strict-combined-acceptance/README.md), sealed by `bbe6a443`.
The selected combination contains bounded `lm_head` (`267ba0b5`), less host overhead (`5c2f849c`),
LDSM activation loading (`eebf689f`) and balanced decode split K (`0eb86cb9`). The latter two are SM120
routes; SM86 keeps the older split choice because the new one regressed its short32 pilot by 1.24%.

| Host                |     short32 before -> after |     chat128 before -> after |
| ------------------- | --------------------------: | --------------------------: |
| Local 5070 Ti       | 9392.66 -> 9866.13 (+5.04%) | 9557.02 -> 9889.77 (+3.48%) |
| 3060 WSL2           |                      +2.61% |                     +0.058% |
| 3060 native Windows |                     +1.018% |                     +0.627% |

These are ABAB means of two round medians, five timed runs per case/process, same token hashes. The
selected source passed **1075 tests on each of Linux and WSL2**, **917 on native Windows**, trained
Qwen parent/canonical +/-/exact restore/EOS on all three, Smol/Tiny on Linux and WSL2, **8/8 new
mutants**, **check-all ALL PASS** (CPU runtime 3252 pass/942 skip; backend 452 pass), Linux packaging and
143-file Worker/SDK Python byte equality. Counts apply to their stated environments, not arbitrary hardware.
The preceding bounded-head implementation separately passed 40 new tests and 10/10 mutants. All open
acceptance items from Claude's original prefill `7ca91112` handoff were addressed in those receipts.

## The remaining gap and how to choose the next experiment

At the present matched control, 80% means **11067.68 token/s**. A 1024-token short32 request must fall
from **103.789 ms to 92.522 ms**: save **11.268 ms**, or 10.856% of wall time / 12.179% more throughput.
This arithmetic is a budget, not a prediction. The owner's explicit warning was to avoid getting stuck
in tiny local optimizations when a larger change in approach may be needed.

The recent positive pilots each suggest around 1%, not the missing 12%. Even a further 5% throughput
gain would reach only about 74.9% of vLLM. A useful next step is an updated whole-request time budget
on the selected source, then a hypothesis that can plausibly save several milliseconds. Inspect existing
receipts before repeating profiling. Do not spend another full acceptance cycle on an isolated faster
kernel until matched whole-request timing supports it.

[Whole-path controls](evidence/2026-10-27-whole-path-controls/README.md), at earlier `267ba0b5`, found
1-token B22/vLLM requests at 37.13/13.26 ms and 32-token requests at 109.10/74.05 ms. Much of the gap was
already present before subsequent decode. Instrumented prefill integer projections summed to 22.2 ms,
prefill attention 2.46 ms. These are **older/instrumented** numbers, not an exclusive breakdown of the
new 103.789 ms control. They justify considering prefill/setup, not only decode.

[Hardware counters](evidence/2026-10-27-strict-counter-profile/README.md) on selected matching-shape
synthetic kernels show cold decode gate/down DRAM throughput 73.56/71.77% and SM throughput 45.95/42.93%.
Prefill gate/down SM throughput is about 70%; bounded head scores DRAM 77.54%; attention DRAM 19.22%.
The earlier claim that all B22 decode GEMMs are near 80% tensor peak is too strong. These counters do
not prove an achievable end-to-end speedup or a B22 ceiling. The old "75–80% ceiling" and Codex's
"73–76% with current approaches" assessment are **judgments, not measured bounds or guarantees**.

Keep the same B22 arithmetic, output bits, tie-breaking and error flags. Do not close the goal with a
longer output budget, easier prompt distribution, prefix deduplication, changed precision, stale candidate
weights or a vLLM wrapper. All parent/candidate/live mutation semantics remain part of the problem.

## Latest eight experiments: final decisions

All are research against selected `0eb86cb9`; none is promoted into runtime source. Each evidence folder
contains retained initial failures, final receipts, a scope-limited README and `seal-01.json`.

| Evidence                                                                               | Result / decision                                                                                                                                                                                                                                               |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Prefill M64, 8 warps](evidence/2026-10-27-strict-prefill-warp-m/README.md)            | 5 CPU-oracle groups, splits 1/3/7, 2/2 mutants. All four real M888 projection shapes regress: large gate about 240 -> 264 us, down 244 -> 263–270 us. Reject; no full-model run. This was the unmeasured next step in the previous HANDOFF and is now finished. |
| [Shorter Newton recurrences](evidence/2026-10-27-strict-newton-cycles/README.md)       | Exhaustive 1,671,934,059 admissible positive FP32 encodings: reciprocal 3 vs 5 iterations differs on 236,645,051; rsqrt 4 vs 6 differs on 25,844,821; union 257,673,297. Reject numerically; no perf claim.                                                     |
| [MMA degree scheduling](evidence/2026-10-27-strict-mma-order/README.md)                | Spread degree dependencies without extra accumulators; 6 CPU-oracle groups, 1 mutant killed. No material warm/cold operator win. Keep original order.                                                                                                           |
| [Attention head tiling](evidence/2026-10-27-strict-attention-head-tiles/README.md)     | 50 operator cases. Two/four-head CTAs increase theoretical occupancy but do not help B32. Some B8/B2 cases improve; do not substitute them for B32. Reject for this goal.                                                                                       |
| [Attention K/V stages](evidence/2026-10-27-strict-attention-key-stages/README.md)      | 60 operator cases plus a separate final-host-helper graph test. Keep 448 threads and ordered 32-key subtrees inside stages of 64/128. Several B32 steps improve 3–5% **for attention only**. Unselected; no whole-request measurement.                          |
| [Cached host TMA maps](evidence/2026-10-27-strict-tma-host-maps/README.md)             | 2 new map tests. Bounded CPU layout templates, API address patches, no cached weight values. Qwen pilot **9990/9992** short/chat; MLP-only **9980/9976**. Token hashes match. Not ABAB; unselected.                                                             |
| [Request-sized KV context](evidence/2026-10-27-strict-request-cache-context/README.md) | 2 CPU-oracle/lifecycle fixture tests. Public max 512 unchanged; physical short/chat contexts 128/272, KV 96/204 MiB instead of 384 MiB. Pilot **9951/9903**, token hashes match. Not ABAB; unselected.                                                          |
| [QKV finish + attention](evidence/2026-10-27-strict-qkv-attention-fusion/README.md)    | 15 operator cases before explicit-context host API correction; GPU kernel unchanged. One final-API graph/live-change/restore/EOS fixture passes. Trained pilot **9865/9862**, no whole-request gain. Park; fewer launches are insufficient.                     |

### If following the small positive candidates

Their helpers are isolated in the evidence folders, not installed. All model pilots hash the final
harness sources and match `bc4a5504e37c79c14e8f6ee824618a85fdd6e0d8d5bcfca51ff1e7691fbd0c66`
(short32) and `a9fad5ca48ed06879bbad136b7282ca0a3c638959dd26e2b1b92635011d5fb49` (chat128).
Do not sum independent percentage gains. An explicit composed adapter followed by baseline/candidate
ABAB is needed to know whether TMA + cache sizing + key staging helps together.

- **TMA host maps:** `HostMapCache` is an OrderedDict capped at 16 entries, keyed by dims/strides/box/
  element size/swizzle. First use calls `cuTensorMapEncodeTiled`; reuse calls the documented
  `cuTensorMapReplaceAddress`, then copies 128 bytes into a 64-byte-aligned CPU argument buffer.
  Two captured nodes sharing this CPU buffer retain their independent by-value maps. The five copied
  transport helpers match the earlier TMA experiment unchanged. The private barrier-timeout error bit
  4 remains unqualified; address the infrastructure-failure ABI before production integration.
- **Cache context:** `BucketGraph` validates with original configured limits/admission, then rounds
  `max(actual_prompt_lengths)+max_new_tokens` up to 16 and uses that physical context in `_DecodeSession`
  and `_decode_core`. A separate nonblocking lock prevents concurrent callers from racing this field.
  Original conservative graph memory accounting is retained. Context changes release the old capture;
  same-bucket requests reuse it. Needs EOS/capacity/stream/parameter-replacement/failure/concurrency tests,
  mutants, trained canonical changes and cross-host qualification before selection.
- **Key stages:** `KeyStageKernels` changes only K/V staging, retaining score nodes and ordered value
  subtrees. Stage128 needs opt-in shared memory; the final helper remembers configured limits so capture
  does not redundantly call `cuFuncSetAttribute`. Initial 60 tests preceded that host-only correction;
  the separate changed-query capture test and operator timings use the final helper. Rerun the final
  module if pursuing it. No mutation or graph-backend integration acceptance exists.

### Unimplemented hypotheses, not results

The last discussed head idea is **coalesced K-parallel exact sparse recomputation**, different from the
already rejected one-thread-per-vocabulary-column SIMT loop. No code or test was written before pause.

One warp would own eight vocabulary columns, each lane processes K indices `lane+32*i`, shares the
same reconstructed activation across eight int64 products, reduces eight integer sums with shuffles,
and encodes once in each of eight publishing lanes. Four warps finish a 32-column surviving tile.
Use the original `bound_q`, `quant_half`, `encode`, tie and error rules; exact int64 bounds must be
documented. A `BoundedLmHead` subclass can override `_functions` and retain the existing bounds/scans.
Write oracle/flag/tail tests first. The original tensor version replicates one row across 16 MMA rows;
the new idea aims to avoid that sparse recomputation cost without serial/uncoalesced K loads.

**Scale warning:** an isolated select cost around 41 us, even eliminated over 31 decode steps, saves only
about 1.27 ms before integration effects. This idea alone cannot bridge the required 11.27 ms. Treat it
as a bounded probe, not the whole strategy. Coarse head scores near 204 us also still scan the live int8
weights. Use actual short/chat prompt activations, not only 32 copies of one prompt, for performance claims.

Another unimplemented geometry is gate/up S1 with row tile **16**, using the old FP32-pair/SiLU handoff.
It doubles the Y grid compared with the rejected M32/S1 variant; it is not yet measured and might still
lose. Do not infer a win from higher occupancy. A warp-specialized TMA producer/consumer pipeline with
register redistribution is also only an idea; no transport/compiler proof exists for it here.

## Earlier directions already measured: avoid repeating blindly

- [Original TMA](evidence/2026-10-27-strict-tma-pipeline/README.md): exact copy/MMA/by-value/capture
  checks passed; large prefill kernels improve 6–7%, but full ABAB only **+0.946%** (9868 -> 9962).
- [Guarded nonlinear normal domains](evidence/2026-10-27-strict-normal-domain/README.md): original
  recurrences match 1.67 billion reciprocal/rsqrt and 2.24 billion exp encodings, 4 mutants caught;
  full pilots about 9888–9908, not compelling ABAB gains. This is distinct from rejected shortened Newton.
- [Guarded QK tree](evidence/2026-10-27-strict-bounded-attention/README.md): 36 tests, 2 mutants,
  full pilot 9896. No selected gain.
- [Concurrent 2 x 16 streams](evidence/2026-10-27-strict-concurrent-batches/README.md): exact tokens,
  but full short32 9858 -> 7200, chat 9852 -> 7732. Reject.
- [M32/S1 gate-up FP32 handoff](evidence/2026-10-27-strict-mlp-traffic/README.md): 6 oracle tests,
  only about 9536 token/s. Reject this geometry.
- [Head hierarchy density](evidence/2026-10-27-strict-head-hierarchy/README.md): 160 actual parent rows,
  5 checkpoints, winner tiles retained, byte bounds match selected. Four-bit bounds retain almost all
  4748 tiles: do not implement int4 -> byte pruning. Seven-bit bounds retain fewer tiles but offer only
  12.5% byte-traffic reduction before unpacking and are unmeasured.
- Other recorded negatives: captured prefill (+0.27%), projection-by-projection weight prepack,
  prefill SiLU fusion, reciprocal lookup, global/native activation fragments, wider attention CTAs,
  side-stream weight prefetch, persistent decode, key splitting and residual/RMS fusion. See the
  [prior summary](HANDOFF.md) and each dated evidence README before reopening a hypothesis.
- B14/mixed arithmetic changes results: the survey changed **5/576 rewards**, ties and ES coefficients.
  It is research, not a strict B22 shortcut. Likewise vLLM/vendor projection controls are not substitutes.

## Reproduction and acceptance mechanics

```bash
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
git status --short
git diff 0eb86cb9 -- runtime/src
nvidia-smi
```

Local Python: `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python`.
Models: `/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/{qwen,smol,tiny}`.
GPU work requires `HETEROES_GPU_ACCEPTANCE=1`, plus `--gpu` where supported. CPU checks use
`CUDA_VISIBLE_DEVICES=''`. Do not alter the `ai` environment or deployed lab.

Every new full-pilot harness supports a baseline switch. Run baseline/candidate/baseline/candidate as
separate processes on an idle GPU, fresh output paths, at least the original five timed repetitions.
Use the existing harness without changing prompts, token counts, context, EOS or prefix policy:

```bash
HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src \
  /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python \
  docs/evidence/2026-10-27-strict-tma-host-maps/harness/bench_full.py \
  --gpu --minimum-work -1 --label baseline-a --out .scratch/FRESH-baseline-a.json
# Same command: --minimum-work 0 for all eligible TMA, or 4000000 for MLP only.
# Request-context harness: omit --bucket for baseline, add --bucket for candidate.
# Fusion harness: omit --fused for baseline, add --fused for candidate (currently parked).
```

For operator pytest, add the folder's `harness` to `PYTHONPATH`; fixture graph tests also need
`runtime/tests/eval`. These experimental tests do not themselves enforce GPU opt-in; set the required
environment explicitly. **No GPU reruns were started during session close.** Final CPU checks cover
syntax, JSON/manifests, source hashes, token hashes and documentation formatting only.

Thảo WSL2 SSH: `ssh -F /home/pc5070ti/.ssh/config -o BatchMode=yes -o ConnectTimeout=8 thao_nguyen@100.92.20.58`.
Remote Python: `/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12`.
Models: `/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models`.
WSL library path:
`/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib`.
Native root: `C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01` (venv and models-prefetch-01).
Earlier pure pytest dependencies: `/tmp/heteroes-codex-testdeps-20261027-01`. Verify remote state before
starting anything; no new SSH work is needed merely to finish reading this handoff.

For selected source changes, preserve AGENTS tests-first and scratch mutation rules. Promotion still
requires meaningful numerical/failure tests, matched whole-request timing, trained canonical +/-/restore/
EOS parity on the relevant hosts, full relevant GPU suites, check-all and source-package byte checks.
Do not rerun all selected `0eb86cb9` acceptance merely because documentation commits have advanced HEAD.

## Closing state

The eight latest research folders are sealed and committed in logical groups. The close audit is in
[session-close evidence](evidence/2026-10-27-codex-claude-close/README.md). `docs/HANDOFF.md` and the local
Claude memory index point here. No optimization is selected beyond `0eb86cb9`, no learning run occurred,
no deployment/lab-state change was made, and M0–M6 remain deferred until after the performance work.
