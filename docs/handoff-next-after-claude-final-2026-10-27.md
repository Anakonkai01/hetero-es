# Handoff after the Claude "final plan" session, 2026-10-27

## Start here

The owner approved a plan on 2026-10-27 (plan file `~/.claude/plans/pasted-content-id-2264-ch-t-reflective-toucan.md`,
summarized below) and then asked to close the session because of usage limits: **"xong việc hiện tại thì chốt phiên
cập nhập handoff đầy đủ để phiên sau làm tiếp"**. The plan is **in progress**, not complete.

- Worktree `/home/pc5070ti/projects/heteroes-codex-frozen-perf`, branch **`work/final-2026-10-27`** (from `a66cfd78`).
  All work is committed locally; nothing pushed, merged or deployed. No GPU job is running.
- Python: `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python`. Models:
  `/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/{qwen,smol,tiny}`. Disk ~5.4 GiB free.
- Nhựt's 5070 Ti stays off. Thảo's 3060 (WSL2 + native Windows) is reachable by SSH key; the plan approval covers GPU
  runs, SSH to Thảo and one deploy after M5. No credentials in the repo.
- Rules unchanged: tests first, scratch mutation checks, evidence README with "What this does NOT show", **no
  Co-Authored-By trailer**, no device approval/contribution changes, no learning runs, no subagents.

## Owner decisions of this session (from the grilling rounds)

1. Performance: one bounded last round; promote at ≥ +1% short32 with equal tokens; close 80% as **not achieved**. Done.
2. M0–M6: do everything doable on the local 5070 Ti and Thảo's 3060 (WSL2 + native); gates needing absent hardware or
   conditions are DEFERRED with a stated reason.
3. Acceptance system: one command `scripts/accept.py` plus receipts and a report with PASS/FAIL/DEFERRED per gate. Done.
4. Order: performance → acceptance → M0–M6 → refactor → deploy.
5. Refactor: move `docs/evidence`, `runtime/artifacts`, `docs/archive` and old handoffs byte-identically to an orphan
   branch `evidence-archive` (main keeps a generated index); remove unselected experiments (B14/mixed, FP16/vLLM views,
   speculative, SGLang/vLLM probes, most of `runtime/scripts`, notebooks, `tests/experiments`) and old product flows,
   keeping everything replay needs; package the strict engine as `heteroes/strict/`; Vietnamese `docs/REVIEW-GUIDE.md`;
   small one-purpose commits; tag `archive/pre-refactor-2026-10` first; never change kernel source text (hash check).
6. B22 (`strict_b22_v1`) becomes the **default for new GPU runs** after the M4 gates; old runs keep their recipe.
7. M6 uses the existing int8 per-row frozen format + LoRA.
8. Finish: fast-forward `main`, `git push origin --all` (no force/tags), deploy **once after the refactored tree passes
   M5** via `scripts/local-lab.py` with rollback to `82c37fc`.

## Done in this session (commits on `work/final-2026-10-27`)

| Commit | What | Evidence |
| --- | --- | --- |
| `e74949c3` | Final perf round: TMA prefill (host map cache), 128-key GQA stages, request-sized KV promoted as SM120 routes with the same bits. ABAB short32 **9871 → 10075 token/s (+2.06%)**, chat128 +0.69%, ≈ **72.8% of vLLM**. TMA timeout now error bit **8** → `StrictTransportError`. 107 tests, 14/14 mutants. | `docs/evidence/2026-10-27-strict-final-composed` |
| `fd0dc863`, `71c27247` | `scripts/accept.py` + `acceptance/` (core, registry, hosts, probes, golden, mutants), `remote --commit` | `docs/acceptance/README.md` |
| `34e0b45c` | M1: `strict_b22_v1` Recipe v3 decoder through the executor (ADR-013): live FP16 weights, chunks 1–64, failures mapped, managed GPU opt-in. 18 tests, 11/11 mutants. | `docs/evidence/2026-10-27-strict-recipe-decoder` |
| `b343beff` | M2 D11: stage-progress heartbeats, persisted hard cap, `hardCapSeconds`/`stallSeconds`. 17 tests, 11/11 mutants. | `docs/evidence/2026-10-27-stage-watchdog` |
| `c8978fbe` | M2 D10: one restore recovery per worker/run under `<worker>~r1`, lab quarantine reconciled. 10/10 mutants. | `docs/evidence/2026-10-27-restore-recovery` |

Promoted-code finding not fixed: the original GQA decode launch fails (`CUDA_ERROR_INVALID_VALUE`) at 692–693 keys
because `gqa_attention_eligible` ignores static shared memory. Loud failure only; fix with a test when touching it.

## Acceptance receipts so far

Tree `src-6c669c56…` (= commit `34e0b45c`): see [STATUS-src-6c669c56.md](acceptance/STATUS-src-6c669c56.md).
**PASS on all three hosts**: strict GPU suite (5070 Ti 1227 s; 3060 WSL2 1592 passed; native Windows 963 passed) and
trained Qwen parent/canonical ±/restore/EOS parity against the golden 0eb86cb9 hashes (Smol/Tiny on Linux/WSL2).
Not yet run through accept.py: `check-all` (cpu), `strict-throughput` (perf), `package-linux`, and the registered
mutation checks (they were run by hand; logs are in the evidence folders). Later commits (D11, D10) changed the source
tree, so the **final acceptance must be rerun on the final tree** for every profile and host.

Before using the throughput gate: `acceptance/golden/throughput.json` still holds a provisional 5070 Ti floor
(9670/9690 = 0.98 × the old 9866/9890). Replace it by 0.98 × the measured promoted value (~10075/9952) and add a
3060 floor after measuring there.

## Continued 2026-10-27 evening (Claude, same branch)

| Commit | What | Evidence |
| --- | --- | --- |
| `79935c39` | D9: the coordinator derives `stop_on_mismatch` from the frozen decoder (`audit_guard.strict_stop_for`); only `strict_b22_v1` stops at the first audit text mismatch. | gate M2.strict-mismatch, 6/6 mutants |
| `d618d4a0` | Audit outcomes for the lab: `v3.audit.run_outcomes` → supervisor `auditSummary.outcomes` → backend → page (matched/mismatched/pending/timed out/skipped/unknown, strict stop, restore faults; EN+VI). New fixture browser check `scripts/check-web-audit-outcomes.mjs` in check-all. | gate M2.audit-ui, 10/10 mutants |
| `f2758f28` | Lab form fields for `hardCapSeconds`/`stallSeconds` (Recipe v3), checked like `validate_watchdog`. | web-experiments browser check |
| `be9f7236` | Prettier ignores acceptance golden/mutant/receipt JSON (the only check-all failure). | check-all otherwise ALL PASS at `f2758f28` |
| `f325fa06`, `1d974461` | M0 probe `acceptance/probes/strict_phase_trace.py` (perf check `strict-phase-trace`); PASS on 5070 Ti and 3060 WSL2, 12 candidate texts equal across the GPUs. Perturb (CPU noise) is the largest warm stage (0.72 s vs 0.26 s rollout). | `docs/evidence/2026-10-27-strict-phase-trace` |
| `2a876685` | M3: streamed hash-checked upload (1 MiB blocks), persisted backoff (`cloud-backoff.json`, 30 s doubling to 1 h), `verify_point(cache=True)` for uploads only, retention keeps newest cloud-verified point and the paused checkpoint. | gates M3.streaming-upload/verify-cache/retention |
| `5e2b91f4` | M3: v3 recovery points carry audit-config, audit-state/gN and audit-stop. | 15/15 recovery-io mutants |

Findings: this worktree's `node_modules` was a symlink to the main checkout, so web builds here bundled the main
checkout's `packages/product-ui`; it is now a local directory of links (environment only, not in Git). Older mutation
checks that start product runs need `--copy scripts` (added for the new groups). The 600-generation soak's
bookkeeping (`published→generation_done` 0.04–6.8 s, `done→recovery point` 0.8–17 s at g540–559) varies far more
than it grows; with a 15 MB ledger it looks like I/O contention, not a growing query. M3.bookkeeping stays OPEN until
the M5 soak measures it.

Still open (in order): M4 (lab/SDK/UI option for `strict_b22_v1` — the backend request model has no `evalDtype` yet,
so the lab cannot create a strict run; qualification keyed by decoder needs a strict model-qualification profile;
D1 GPU ownership; strict default), M5 (`strict_e2e.py` never run), M6, final acceptance, refactor, push, deploy.

## Next steps, in order

1. **M2 remainder.** D9: enable the existing strict first-mismatch primitive (`runtime/docs/audit-state-v1.md`,
   `v3/audit_guard.py`) for `strict_b22_v1` recipes only, with tests; audit outcome projection to supervisor/backend/UI
   and translations (list in `docs/HUMAN-REVIEW-EFFORT-SPLIT.md`); lab UI fields for `hardCapSeconds`/`stallSeconds`.
2. **M0 remainder.** Per-phase trace + peak memory receipt of the strict executor on trained Qwen (phase_trace exists).
3. **M3.** Bounded streaming recovery upload (no whole-object `read()`), stateful backoff, verify cache tied to
   manifest + file identity, retention dependency graph, early/middle/late bookkeeping cost (1.7 s → 11 s over 600
   generations). Real full-disk acceptance stays DEFERRED (owner decision 2026-10-23).
4. **M4.** Lab/SDK/UI option for `strict_b22_v1` (frontend `RuntimeConfiguration.tsx` lists decoders by hand; backend
   `validation.py`; SDK `ESConfig`), qualification keyed by decoder (backend `v3_qualification` ignores the decoder
   today), D1 GPU ownership (coordinator validation/export on the same GPU), make strict the default for new GPU runs.
   Note: managed product runs only carry `evalDtype`/`evalChunks` into documents for strict runs
   (`product/v3.strict_options`) so earlier runs resume with identical documents — keep that property.
5. **M5.** `acceptance/probes/strict_e2e.py` is written but **never run**: CPU coordinator here, local 5070 Ti worker,
   remote 3060 WSL2 worker, `strict_b22_v1`, subset weights, audits 0.5; checks re-scoring, CPU replay of every child
   hash and cross-GPU audit matches. Run it (`python3 acceptance/probes/strict_e2e.py --out .scratch/e2e-01`), fix what
   breaks (e.g. a strict decoder on a CPU coordinator if it validates checkpoints), register it as a gate, then a soak
   (600 generations if time allows, else DEFERRED with the reason), release notes with rollback.
6. **M6.** int8 frozen base (`eval/frozen_int8*.py`, `model/frozen_int8.py`) + LoRA through the executor/lifecycle,
   no dequantized shadow, peak VRAM per phase, cross-host parity.
7. **Final acceptance** on the final tree (all profiles, three hosts), regenerate `docs/acceptance/STATUS.md`.
8. **Refactor** exactly as decision 5, keeping `accept.py cpu` green per commit, then rerun everything.
9. Fast-forward `main`, push, deploy once, verify (`scripts/verify-public-lab.py`), clean old worktrees, update
   HANDOFF and memory.

## Commands

```bash
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
python3 scripts/accept.py list
HETEROES_GPU_ACCEPTANCE=1 python3 scripts/accept.py run gpu perf --keep
python3 scripts/accept.py remote 3060-wsl gpu --keep          # commit first, or --commit <rev>
python3 scripts/accept.py remote 3060-native gpu --keep
python3 scripts/accept.py report --write
```

The full local GPU suite takes ~20 min, WSL2 ~18 min, native ~22 min; the 3060 is one physical GPU, so run WSL2 and
native one after the other. Do not measure throughput while other GPU or heavy CPU work runs.
