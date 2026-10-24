# Human-review implementation — handoff to Claude

The owner requested this handoff on 2026-10-24 after pausing Codex auto-run to conserve usage. Continue the approved
implementation; the overall objective is **not complete**. No new kernel was started after the pause. All probes/check
sessions started here returned terminal status; no acceptance run was deliberately left running. Revalidate external
state before continuing. This handoff does not resume the paused Codex goal.

## Claude session result (2026-10-24 evening) — read this first, then hand to Codex

Commits on the branch after `aae2671`: `e7b39cd` (audited NVRTC linear kernel), `282e7c6` (fused-op kernels,
`Qwen2StrictCuda`, probe, comparison script, four-GPU receipts), `1cf0843` (M2: v3 scoring outside the lock).
No push, merge, deployment, lab or device-state change. The local lab services were not running at session start;
they were left alone.

- **M1 kernel gate reached on a finite matrix.** `eval/strict_cuda.py`: linear, RMSNorm, residual add, SiLU gate,
  RoPE, attention/softmax. They give the same bits as `reference_ops`, per kernel and per graph, and pass PTX/SASS
  audits. `eval/qwen2_strict_cuda.py` runs the Qwen2 graph on them. The pinned Qwen2.5-0.5B (parent + 8 antithetic
  candidates × 8 prompts, 4,387 tokens) agrees on the local 5070 Ti, **Nhựt's 5070 Ti** (`heheboiz@100.108.195.50`,
  native Linux, driver 580; the owner added it this session), Thao 3060 and Quang 3060 (WSL2).
  ~60 tokens/s on a 5070 Ti, ~24 on a 3060; peak ~1.08 GB. Receipts, equivalent mutants and limits:
  `docs/evidence/2026-10-24-strict-cuda/README.md`.
- Remote runs used fresh `/tmp/heteroes-strict-20261024-*` directories and each host's existing Python, read-only.
  Pure-Python pytest wheels were added on `PYTHONPATH` from the scratch directory; nothing was installed.
  Nhựt's model is at `~/.local/share/heteroes-worker/models/7ae557604adf67be50417f59c2c2f167def9a775`; Python is
  `~/.local/share/heteroes-worker/runtimes/bf28fa656ad4/python/bin/python3`. His worker service was running but idle.
  Do not touch it.
- **M2 started (`1cf0843`):** `WorkerAPI._submit_texts` validates under the lock, scores outside it, makes
  identical in-flight submissions wait for one scoring, then commits under the lock. The ledger re-checks for a
  stale attempt. An identical retry of a committed result returns ALREADY_COMMITTED without scoring. `AuditAPI`
  forwards non-audit, non-lease operations without its own lock. Tests: `tests/ledger/test_worker_api_concurrency.py`;
  ledger+v3 suites pass. **Mutation check for this change has NOT been run yet: do it first.** The usage sink is still
  called synchronously, outside the lock (W3 item 5: bounded queue still open).

### Next actions for Codex (in order)

1. Mutation-check `1cf0843` (scratch copy, `scripts/mutation-check.py`): leader/waiter, the fast-path digest
   compare, the audit lock bypass.
2. Continue M2: heartbeat across delivery/pending retries and a durable outbox (`worker.py`); local poison on restore
   fault; usage bounded queue; audit rate in SDK/API/UI; selected/completed/matched/mismatched/timed-out/skipped
   states; stage watchdog plus explicit hard caps; the restore-recovery state machine (D10). Then M3 (bounded
   streaming upload/backoff in `product/cloud_sync.py`).
3. M1 remainder: precompute RoPE tables once per backend (eager `sin_cos` per forward costs time). Reduce Python
   launch overhead (cache argument arrays, or CUDA graphs per decode step). Add a multi-row linear (ILP over rows)
   and batched multi-sequence decode; row independence is already tested. Measure native HF FP16 for the same
   prompts, then propose thresholds to the owner.
4. Native Windows: not run. The tailscale node `desktop-qp0nta7-1` (100.81.45.107, Windows) may be Thao's Windows
   side. **SSH to it was not authorized: ask the owner.**
5. M4 integration (recipe/backend identity, qualification cache keyed by backend, GPU ownership across roles,
   packaging so that kernels and `cuda-bindings` reach workers), then M5 and M6, as in the plan.

## Read first

1. [AGENTS.md](../AGENTS.md), then [HANDOFF.md](HANDOFF.md).
2. Approved full plan, outside the repo:
   `/home/pc5070ti/projects/heteroes-review-2026-10-24/PLAN-SUA-HUMAN-REVIEW.md`.
   Original review: `/home/pc5070ti/projects/human-review.md`. Historical inventory/open-decisions notes are in the
   sibling review directory. Use the current implementation status for progress, not the plan's initial-state prose.
3. [ADR-012](../runtime/docs/adr/ADR-012-single-model-strict-inference.md),
   [implementation status](HUMAN-REVIEW-IMPLEMENTATION.md),
   [numerical contract](../runtime/docs/numerical-contract.md),
   [experimental operation specification](../runtime/docs/strict-reference-v1.md).
4. [Reference evidence and limits](evidence/2026-10-24-human-review/reference-summary.md).

## Repository and authorization

- Repo: `/home/pc5070ti/projects/heteroes`; branch `fix/human-review-single-model-2026-10-24`; base `c9997734`.
- Implementation head: `3914fb5`; the subsequent handoff commit changes documentation only. Worktree was clean before
  the handoff edits. Commits: `ef36646` (phase/storage telemetry, ADR), `fe6c201` (lifecycle profiler), `3914fb5`
  (experimental Qwen reference, probes, receipts). No push, merge or deployment in this work.
- Owner approved the full plan, autonomous implementation, GPU experiments and SSH to both named 3060 hosts.
  Do not reconfirm settled decisions. This does not authorize lab deployment, device approval/contribution changes
  or a learning run. Keep the existing `ai` environment unchanged. No global driver configuration was changed.
- Current AGENTS.md overrides contrary instructions in historical handoffs. Preserve historical numerical identity;
  frozen noise/ES/ledger code is not a general refactoring target. Write meaningful tests before behavior, mutation-check
  scratch copies, retain intermediate failures and commit logical groups.
- Existing evidence is immutable, including failed receipts and raw log whitespace. Use fresh names/folders.
  Never write credentials into documents, logs or commits. SSH keys worked; sudo was not needed.

## Owner decisions: already settled

| Requirement     | Agreed meaning                                                                                                                                                                                                                                                                    |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One model       | One full set of inference weights per physical GPU across **all managed roles/processes**, including worker, coordinator validation, profiling and export/reload. Share a runtime or serialize phases. Bounded FP32 workspace is allowed.                                         |
| Equality        | Same candidate/input must produce the same token IDs/text and reward across supported heterogeneous NVIDIA GPUs. Equal intermediate logits are not required. Homogeneous-only support is unacceptable.                                                                            |
| Compatibility   | A new versioned backend/recipe may differ from historical FP32 output. Preserve old recipe hashes, noise/update rules, publication and recorded replay.                                                                                                                           |
| Precision scope | FP16 full/subset ES first, then frozen quantized base with ES LoRA. Full quantized-weight ES is separate research. Precision profiles need their own identity.                                                                                                                    |
| Restore         | CPU parent snapshot is allowed, limited to trainable schema; restore must be exact.                                                                                                                                                                                               |
| Hardware/models | NVIDIA on Linux and native Windows; pinned Qwen2.5-0.5B first, expand by model-family/operator coverage.                                                                                                                                                                          |
| Audit           | New strict-path text mismatch stops before the next update and preserves evidence. Neither worker is assumed correct. Incomplete coverage is separate; preserve the existing partial-coverage policy until explicitly changed.                                                    |
| Worker recovery | One clean automatic recovery per worker/run after a restore-only mismatch, persisted across restart: stop locally, persist/report fault, reload canonical parent, verify/self-test/probate, rejoin at a generation boundary. Repeated faults/inference mismatch need an operator. |
| Watchdog        | Stage/progress watchdog plus finite, explicitly configured researcher/operator hard caps. Heartbeat proves connectivity, not computation progress.                                                                                                                                |

Keep oomd/host usability, essential replay/result data until owner deletion, and the existing one-coordinator-recovery
limit. Real full-disk acceptance remains explicitly deferred. See the full plan and operations decisions.

## Implemented: M0 partial, M1 experimental only

M2–M6 are not implemented. The managed/default inference path still has its old lifecycle and shadows; this work has
not replaced it. No optimized CUDA kernel exists.

- `runtime/src/heteroes/eval/phase_trace.py`: opt-in host phase traces and unique backing-storage inventory.
  `executor.py` traces perturb/refresh/rollout/restore without changing legacy timing meanings or recipe numerics.
  Host wall timing is not CUDA kernel elapsed time; storage inventory is not allocator/process peak memory.
- `runtime/scripts/profile_single_model.py`: local-safetensors lifecycle probe, native FP16 or `--backend qwen2-reference`.
  One live model, permitted CPU snapshot, perturb/generate/exact restore, parent hashes, timings and memory receipts.
- `eval/reference_ops.py`: explicit FP32 boundaries with subnormals flushed to signed zero, fixed adjacent-pair tree
  with odd-tail carry, bounded FP16 weight widening, specified nonlinearities, RMSNorm and masked softmax. Nonfinite/
  unsupported domains fail. No vendor GEMM/transcendental fallback. Read the specification before optimizing.
- `eval/qwen2_reference.py`: manual Qwen graph using the **same live FP16 weights**; no deepcopy, full FP32 weight
  shadow or HF forward. FP32 KV cache is local to a generation call. Prompts are packed and processed serially to
  remove batch/padding dependence. Explicit greedy ties, EOS/padding, repetition penalty and scope validation.
  Source/config/constants are fingerprinted; `hardwareQualified` remains false.
- `runtime/scripts/probe_reference_backend.py`: portable deterministic tiny-Qwen/operator probe with parent/candidate
  hashes, logits/tokens/rewards and restore. Its fixture flag cannot qualify the real-model configuration.
- Tests: `runtime/tests/eval/test_{phase_trace,profile_single_model,reference_ops,qwen2_reference,probe_reference_backend}.py`.

## Evidence and its limits

Folder: `docs/evidence/2026-10-24-human-review/`.

- Tiny fixture agrees bit-for-bit on CPU, 5070 Ti, Quang 3060 and Thao 3060 (WSL2): seven operator hashes, four graph
  cases per target, parent/candidate weight hashes, logits, tokens, rewards and exact restore.
- Real Qwen 0.5B agrees on **one prompt, one perturbed candidate and one new token** per target: seed 7001, sigma .001,
  token `[17607]`, text ` ?\n`, last-integer reward zero. All restores pass. This full-model probe does not separately
  record the perturbed-weight hash. It is not a quality/learning result or broad inference acceptance.
- Full-model rollout host wall: CPU 49.414 s; 5070 Ti 46.325 s; Quang 3060 144.651 s; Thao 3060 148.679 s.
  The eager reference is much too slow for promotion.
- Live weights/buffers/constants: 988,065,920 B; allowed CPU snapshot: 988,065,536 B. GPU peak allocated:
  1,076,176,896 B; peak reserved: 1,203,765,248 B. This is a standalone process, not proof of managed cross-process
  ownership on the physical GPU.
- `reference-comparison-01.json` independently compares raw receipts and hashes its inputs.
- `reference-mutation-02.log`: 14/14 numerical/memory/graph defects detected. Initial 13/14 receipt is retained;
  the memory guard missed `aten::to` and was fixed. `reference-probe-mutation-01.log`: 5/5 probe defects detected.
- Full CPU checks: 2,725 runtime tests passed, 105 skipped; 439 backend tests passed. Source packages, format/lint,
  types, i18n, UI units/build and fixture browser/Electron checks ran. Sole initial failure: a stale live-view test
  selector combined device name and GPU detail. It now checks both; targeted browser rerun passes. Read
  `checks-reference-overview-01.json`; do not relabel the original check-all run as an unqualified ALL PASS.
- Native Windows, broader corpus, managed lifecycle, end-to-end ES, quantization and default promotion remain open.

## Next actions

1. Stress-test the reference, then implement a checked fast linear projection reading FP16 weights directly. Preserve
   the exact tree, odd tails, FP32 rounding, signed zero/FTZ, bias and nonfinite failure behavior; ordinary deterministic
   vendor GEMM is insufficient.
2. Write tests first: independent CPU/reference oracle, cancellation/extremes, K=1/odd/real Qwen dimensions, bias,
   zero signs, unsupported inputs, execution tiles/streams and bounded memory. Check guards before CUDA access;
   mutation-check deliberate defects.
3. A possible route, **not implemented or accepted as final design**: NVRTC + CUDA driver bindings with explicit PTX
   rounded add/multiply and FTZ. In-place parallel tree writes can race; prove synchronization/storage behavior.
   Inspect generated instructions for contraction/reassociation and record build details. Keep a native Windows route.
4. Compare primitive bits, then graph/cache/padding/batches and parent/perturbed token streams on both GPU architectures.
   Add candidate hashes to the full-model probe. Measure warm/cold cost/memory before proposing thresholds; avoid
   spending hours repeating the slow eager corpus.
5. Integrate recipe/backend identity, admission/qualification/profiling caches and capabilities after the relevant gates.
   Preserve legacy identities. Cover shared/serialized ownership across worker/coordinator/validation/export/processes.
6. Continue independent M2/M3 work as well. M4/M5 system acceptance and M6 quantized base + LoRA remain in scope.
   Do not shrink completion to a fast kernel or a passing small model.

The final read-only environment query found `cuda-bindings` 13.3.1 and NVRTC 13.2 with torch 2.13.0+cu132. No compiler
prototype or new kernel files were created. Primary references:
[NVRTC](https://docs.nvidia.com/cuda/nvrtc/),
[CUDA Python](https://nvidia.github.io/cuda-python/cuda-bindings/13.3.2/overview.html),
[NVIDIA floating point](https://docs.nvidia.com/cuda/floating-point/index.html).

## Reliability source map: findings, not fixes

- `worker_api.py`: global lock spans scorer/commit/usage; identical committed texts can be rescored before
  ALREADY_COMMITTED. Use brief validation/authentication, scoring outside lock, attempt revalidation at atomic commit,
  concurrent-duplicate coalescing and preserved stale/conflict semantics. Check the outer lock in `v3/audit.py` too.
  Usage cannot undo/misreport a canonical commit. Do not promise exactly-once external scorer effects across crashes.
- `worker.py`: heartbeat ends after evaluation, before delivery/pending retries. Preserve it until terminal ACK/
  rejection, add durable delivery/fault state, and poison locally immediately on restore fault even when reporting
  loses the network. Transport retry must not allow dirty weights to acquire work.
- Reconcile ledger quarantine, audit fault file and supervisor quarantine, late restore-fault holders and the persisted
  once-per-worker/run recovery allowance. Do not reset the coordinator recovery cap.
- `coordinator.py`, `product/runner.py`: timeout/history fallback and heartbeat activity are not progress watchdogs.
  Expose explicit finite caps; do not replace the 1,800 s floor with another guessed default.
- `v3/audit.py`, SDK/lab config: expose rate 0..1, default .05; distinguish selected/completed/matched/mismatched/
  timed-out/skipped. First-mismatch stop belongs to the new strict path; preserve historical policy/replay meaning.
- `http_transport.py`: 1 MiB body limit can reject full text batches. Measure encoded bytes and design bounded
  delivery without changing trust to reward-only submissions.
- `product/cloud_sync.py`: full-object memory reads, repeated rehash/scans and finished-run retries need bounded
  streaming, backoff/scanning and verification while retaining corruption detection and essential data. Historical
  I/O evidence exists; oomd causality is not proven.
- `eval/precision.py`, `v3/tracker.py`, `product/chunk_memory.py`, local process orchestration: shadows and export/reload
  overlap violate the new lifecycle. Schema/LoRA/publication assume FP16. Namespace qualification/profiles by backend;
  old receipts cannot certify the new prototype. Generated noise threshold constants are intentionally kept.

Read the full plan for the complete checklist and `operations-decisions-2026-10-23.md` for retention/recovery policy.

## Environment and hardware access

Local Python: `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python` (3.12.14).
Backend Python/Ruff: `.venv-backend/bin/python`, `.venv-backend/bin/ruff`.
Local torch 2.13.0+cu132, transformers 5.17.0, NumPy 2.5.3; RTX 5070 Ti 16 GB, driver 595.91.07.

| Target | SSH                        | Python                                                                                       | Model directory                                                                                                             |
| ------ | -------------------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Thao   | `thao_nguyen@100.92.20.58` | `/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12` | `/home/thao_nguyen/.local/share/heteroes-c4-cpu/models/7ae557604adf67be50417f59c2c2f167def9a775`                            |
| Quang  | `quang@100.99.227.8`       | `/home/quang/heteroes-venv/bin/python`                                                       | `/home/quang/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775` |

Both remote GPUs: 12 GB RTX 3060, driver 617.42 through WSL2, **not native Windows acceptance**. Thao Python 3.12.15,
Quang 3.14.4; both torch 2.13.0+cu132/transformers 5.17.0 at observation.
Use `ssh -F /home/pc5070ti/.ssh/config -o BatchMode=yes ...`; system SSH config had an ownership error.
Old socket/device-denial receipts describe the earlier sandbox; permissions were subsequently updated.

Use a process-local library path for remote probes:

```bash
LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib
```

Revalidate the directory after driver updates. Quang otherwise segfaulted in the system Linux JIT library
`libnvidia-ptxjitcompiler.so.580.178.04` during CUDA discovery. No apt driver installation, sudo or global library edit
was used. WSL `nvidia-smi`: `/usr/lib/wsl/lib/nvidia-smi`.
Copied sources/receipts remain at `/tmp/heteroes-review-20261024-01` on both hosts. Use fresh scratch for changed
sources; do not overwrite old receipts or operate enrolled worker/lab state.

Local pinned model:
`/home/pc5070ti/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775`.

Small CPU probe from repo root, with a fresh receipt path:

```bash
CUDA_VISIBLE_DEVICES='' PYTHONPATH=runtime/src \
  /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python \
  runtime/scripts/probe_reference_backend.py --out .scratch/claude-reference/cpu-01.json
```

GPU probe: remove `CUDA_VISIBLE_DEVICES=''`, set `HETEROES_GPU_ACCEPTANCE=1`, add `--device cuda --gpu`, use a fresh
receipt. Full-model probe: `profile_single_model.py --model-path <pinned-dir> --backend qwen2-reference`; bound tokens/
candidates explicitly because it is slow. Run applicable AGENTS.md checks. Full check-all uses fixture ports
18090–18095; run it alone and do not edit/build its inputs while active.

Completion still means the full approved plan: one managed weight set per GPU, qualified heterogeneous inference,
reliability/recovery fixes, integration/packaging/system acceptance, then quantized-base/LoRA gates. Report gaps honestly.
