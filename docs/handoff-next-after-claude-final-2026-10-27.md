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

`8d52b76c` (M4 part 1): strict model qualification keyed by decoder (`qualification_key`), probe agent keeps
engine+decoder (fixed a real bug: v2 first probes built v1 references), backend accepts `evalDtype` for the strict
decoder only and checks strict qualification per selected device. No mutation check yet for this slice.

### Routine items 1–3 done (Sonnet 5.5 session, same evening)

| Commit | What | Evidence |
| --- | --- | --- |
| `61272cda` | Mutation check for `8d52b76c`: 13/13 runtime and 16/16 backend mutants killed after 4 new tests (first run left 7 alive; 1 equivalent mutant removed). Registered as `mutation-strict-qualification-runtime`/`-backend` under gate `M4.qualification` (now has checks, no longer OPEN). | `docs/evidence/2026-10-27-strict-qualification` |
| `4ad21b7e` | Lab UI: `strict_b22_v1` in the Recipe v3 form (sends `evalDtype: "float16"`, only then), Models page "Decoder" choice (strict forces noise engine v2, starts the check with `decoder`), EN+VI strings, fixture browser checks in `check-web-model-qualification.mjs` and `check-web-experiments.mjs` (strict attempt is refused without the strict check; a plain draft carries no `evalDtype`). | check-all |
| `10ceac91`, `90ef6abd` | Throughput floors: 5070 Ti 9873.1 / 9753.0 (0.98 × promoted ABAB mean; fresh local run 10138 / 9963 passes); 3060 WSL2 3041.6 / 2867.2 (two runs 3100.1/3107.3 and 2924.0/2927.4). Native Windows has no throughput check. | `acceptance/golden/throughput.json` |
| this commit | `check-all` PASS through accept.py on this tree (`docs/acceptance/receipts/2026-10-27T1901-local-cpu.json`). | |

Not done on purpose: `docs/acceptance/STATUS.md` is regenerated only after the final acceptance (every other receipt belongs to an
older tree, so today it would show NOT_RUN). Gate `M4.identity` still says "no recipe field selects the strict backend"; that text
looks stale since `strict_b22_v1` is a Recipe v3 decoder (ADR-013) — check it and give it its checks when doing item 5. The mutation
profile (`accept.py run mutation`) was not rerun as a whole.

### Remaining work, by difficulty (for choosing the model)

Routine (a Sonnet-class session can do it, following the existing patterns and tests). **Items 1–3 are done, see above; item 4 waits for the final tree.**
1. Mutation check for `8d52b76c` (mutants: drop decoder from `qualification_key`, accept any decoder in `accept`,
   ignore decoder in `v3_qualification`, drop `decoder` from the frozen probe command) and register it in accept.py.
2. Frontend: decoder option `strict_b22_v1` in `RuntimeConfiguration.tsx` (v3 only, sends `evalDtype: "float16"`),
   a "Qualify for strict decoder" action on the Models page (POST `.../qualifications` with `decoder`), translations,
   browser check. SDK `ESConfig` already has `eval_dtype`; check `sdk_lab` passes the decoder to qualification.
3. Throughput floor in `acceptance/golden/throughput.json` (0.98 × measured), `check-all` + `accept.py report --write`.
4. Final acceptance reruns on three hosts (commands below), release notes, push and deploy steps as written.

Harder (better for a stronger model, or with the owner present):
5. M4 D1 GPU ownership (coordinator validation/export on the same GPU as a worker) and making strict the default
   for new GPU runs only after the gates — touches scheduling/reservations.
6. M5 `acceptance/probes/strict_e2e.py` has never run: first two-GPU end-to-end strict run (CPU coordinator, local
   5070 Ti, 3060 WSL2). Debugging whatever breaks there crosses coordinator/worker/network code. Then the soak, where
   M3.bookkeeping must be measured (see findings above).
7. M6 int8 frozen base + LoRA through the executor (`eval/frozen_int8*.py`, `model/frozen_int8.py`): numerical work.
8. The refactor (decision 5): moving evidence to an orphan branch and removing experiments safely is large but
   mechanical; it needs care with replay dependencies and kernel-source hash checks.

## Continued 2026-10-27 night → 10-28 (Opus 5.5 session): hard items 5–7 done, refactor left

The owner said "tiếp tục" (continue), then on 2026-10-28: **"về refactor thì để phiên claude sau làm, cập nhập handoff
đầy đủ để phiên sau làm"**: the refactor goes to the next Claude session. HEAD **`563303eb`**, branch
`work/final-2026-10-27`, nothing pushed, merged or deployed. No GPU job is running.

| Commit | What | Evidence / check |
| --- | --- | --- |
| `f77c7225` | M5 e2e probe: the fixture's answers were strings, so `last-integer` scored every text 0 and the first run passed trivially. Answers are integers now; the probe fails when no update changed the weights; `--kill-local-at N` (SIGKILL the local worker 1 s after generation N opens, restart 30 s later, an expired lease is required), `--compare`, `--weights`, bookkeeping thirds. | check `strict-e2e` (faults) |
| `012acebf` | M4 D1 for strict runs: the lab refuses a strict run on a CPU-only coordinator (its validation/export use the strict decoder: before this the run would have failed at its first validation) and one whose coordinator device or physical GPU is one of its workers (`policies.strict_layout`, at creation, scheduling and joins). Export reload only after the live model and its strict engine left the GPU (`Tracker._release_device`). Lab form: new Recipe v3 run defaults to `strict_b22_v1`. SDK: `Lab.qualify(decoder=)`, `evalDtype` sent only for strict, FP16 only with strict; `ESConfig` default unchanged on purpose (ADR-013 amendment). | mutation 8/8 backend, 9/9 runtime; gates M4.identity/gpu-ownership/default |
| `89215f18` | M5 evidence: plain, fault and 600-generation runs, CPU coordinator + 5070 Ti + 3060 WSL2, `strict_b22_v1`. All E2E OK; fault run gives the same children and generation records as the plain run; soak 2371/2371 cross-GPU audits matched, 3060 did 1572/4800 results, coordinator bookkeeping flat (record 4.6/4.8/4.5 ms, generation 1.03/0.99/0.98 s). | `docs/evidence/2026-10-27-strict-e2e` |
| `bbd6fe7b` | M6 `strict_int8_lora_v1` (ADR-014): frozen int8 base (per-row int8 of the LoRA targets, no FP16 copy left) + FP16 LoRA as the only parameters; weight space LoRA + `frozenBaseSha256` checked on every worker; `FrozenInt8DecoderGraph` through `strict_backend`; strict chunks, audit stop. Standalone/SDK only: the lab and the SDK lab bridge refuse it, coordinator export refuses it. | `runtime/tests/v3/test_v3_int8_lora.py` |
| `563303eb` | M6 checks: `int8_memory.py` (5070 Ti, Qwen, 7 projection kinds: peak 953 MiB while the FP16 model loads, 611 MiB frozen, 711 MiB per candidate, exact restore), `strict-e2e-int8` (two GPUs, 14/14 audits matched, CPU replay of every adapter child), mutation 14/14. | gate M6.lora-lifecycle |

Gates now: every M0–M6 gate has checks except **M3.bookkeeping (OPEN)**, **M5.long-run (OPEN: the soak above exists,
but it is not registered as a check yet: register it, e.g. `strict-e2e --generations 600 --weights
'layers\.23\.self_attn\.o_proj'`, or point the gate at the evidence)**, **M5.release (OPEN)**, and the deferred
M1.architectures / M3.full-disk.

Findings not fixed:
- Two captured strict engines in one process on one GPU (`python -m heteroes.v3 run --workers 2 --device cuda`) fail
  during CUDA graph capture ("operation failed due to a previous error during capture"). The lab never does this;
  the int8 GPU test uses one worker. Fix with a process-wide capture lock if wanted.
- M3.bookkeeping: the strict soak used the standalone coordinator, not the product runner with recovery points, so the
  earlier 1.7 s → 11 s growth is still unmeasured there.
- A strict lab run needs two GPUs (one coordinates). Lifting this needs coordinator validation inside a worker's
  runtime (or validation leased to workers): not built (ADR-013 amendment, point 2).
- `int8_memory.py` reported reward 0 for its one candidate with all seven projection kinds frozen and sigma 0.02;
  the e2e run (q/k/v/o only) started at mean reward 0.64. No quality claim is made for the int8 base.
- Disk: ~4.6 GiB free. `.scratch/` holds 8.3 GiB of earlier sessions' scratch (not deleted); the e2e/soak runs of this
  session are `.scratch/e2e-0*`, `.scratch/soak-600`, `.scratch/e2e-int8-01` (published weights already removed for
  e2e-01..03). Clean what is not needed before long runs.

### What the next session does (in order)

1. **Refactor** exactly as owner decision 5 above (plan file `~/.claude/plans/pasted-content-id-2264-ch-t-reflective-toucan.md`,
   section "Bước 4"). Notes from a first survey (nothing changed yet):
   - tag `archive/pre-refactor-2026-10` at HEAD first (local tag; never push tags);
   - `docs/evidence` (223 folders, 11 079 files), `runtime/artifacts` (2 694), `docs/archive` (83) and the old
     `docs/handoff-*.md` go to the orphan branch `evidence-archive` built from the same blobs (temporary index +
     `git update-index --index-info` from `git ls-tree -r HEAD -- <paths>`, `write-tree`, `commit-tree`); prove equality
     by comparing `git ls-tree -r` blob SHAs;
   - files that READ those paths (fixtures to copy into `runtime/tests/fixtures` / `backend/tests/fixtures`):
     `backend/tests/{test_devices,test_noise_engines,test_v3_study,test_worker_cli_lab,test_worker_profile}.py`,
     `runtime/tests/eval/{test_candidate,test_compare_records,test_generate,test_workload}.py` and the others listed by
     `git grep -l "docs/evidence\|runtime/artifacts\|artifacts/" -- '*.py' '*.sh' '*.mjs' '*.ts'`; many hits are only
     comments citing evidence (keep them, they now point into the archive branch). Also check
     `scripts/build-apps.sh`, `scripts/build-worker-profile.py`, `scripts/publish-local-installers.py`,
     `backend/deployment.py` before deleting anything. Simplest reliable loop: delete in the tree, run
     `scripts/accept.py run cpu` + `package`, fix what breaks;
   - 8 evidence folders have no README (e.g. `2026-10-12-local-portability`, `2026-10-21-candidate7-device-upgrades`):
     the generated `docs/EVIDENCE-INDEX.md` must list them anyway;
   - then experiments/legacy removal by an AST import graph from the real entry points, `heteroes/strict/` package with
     a kernel-source hash check before/after, file splits, `docs/REVIEW-GUIDE.md` (Vietnamese). Small commits, each
     with `accept.py run cpu` green.
2. **Final acceptance on the refactored tree**: `HETEROES_GPU_ACCEPTANCE=1 python3 scripts/accept.py run cpu gpu perf
   faults package mutation --keep`, then `remote 3060-wsl gpu perf --keep`, `remote 3060-native gpu --keep` (one after
   the other, same physical GPU), `report --write` → `docs/acceptance/STATUS.md`. New checks since the last receipts:
   `strict-e2e`, `strict-e2e-int8` (faults, use SSH to Thảo), `int8-memory` (perf, local + 3060-wsl),
   `mutation-gpu-ownership-*`, `mutation-int8-lora`. Register the soak for M5.long-run; write release notes and a
   rollback rehearsal for M5.release.
3. Fast-forward `main`, `git push origin --all` (no force, no tags), deploy once with `scripts/local-lab.py`
   (rollback `82c37fc`), `scripts/verify-public-lab.py`. The lab services were all down at the last status read
   (2026-10-27 evening); do not change device states.

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
