# Handoff — Recipe v3 / extensible experiments (for any agent continuing this work)

Written 2026-10-19 at the end of a long session. Read `../AGENTS.md` (common rules) and `HANDOFF.md` first; this file is
the detailed state and plan of ONE workstream: making HeteroES a platform where other people design their own ES
experiments (model, data, reward, weight space, sampling) instead of running the author's built-in ones.

## 1. Where things are

- Repository `~/projects/heteroes`, branch **`feat/extensibility-step0`**, based on `086c282` (local `main`). About 20
  commits, **not merged into `main`, never pushed** (pushing and merging are the owner's call). The live lab runs from a
  separate deployed clone (`~/.local/share/heteroes-lab/app`) and is NOT affected by this branch.
- Design: **`runtime/docs/adr/ADR-008-recipe-v3-and-extensible-experiments.md`**, status ACCEPTED (owner, 2026-10-19).
- User guide of what works today: **`runtime/docs/v3-local-runs.md`**.
- Receipts, one folder per step (each has a README with "What this does NOT show"):
  `docs/evidence/2026-10-19-extensibility-{step0,step1,subset,lora}`, `docs/evidence/2026-10-19-v3-{ledger-record,protocol,local-sdk}`.
- The audit that started it (hard-code map, TRL comparison, grill decisions) is outside the repository:
  `~/.claude/plans/y-l-c-i-prompt-deep-cupcake.md`. Its decisions are copied below; you do not need the file.

## 2. Owner decisions (final — do not reopen them)

| # | Decision |
| --- | --- |
| Q1 | Reward is computed **on the coordinator** from the texts the worker submits. |
| Q2 | Texts are **ledger data**: first committed attempt wins; replay re-scores stored texts; drift is found by sampled re-execution (audit). |
| Q3 | The scorer's identity (name@version + code SHA-256) is **outside the recipe hash**, frozen per generation in the generation context. |
| Q4 | **Hybrid**: a shared lab accepts only declarative scorers; Python scorers run only on a coordinator the researcher hosts. |
| Q5 | Weight spaces **full, subset and LoRA** (owner chose LoRA against the AI's advice: research comparison, PEFT export, light sync). LoRA results are never mixed with full-parameter results. |
| Q6 | **Merge v1 and v2 into one format** (owner chose a format merge, not a code-only merge). Numerics unchanged; old runs must replay to their recorded hashes; old artifacts are never rewritten. |
| Q7 | **One identity break** (v3, desktop r11) carrying signs, coefficient rule, weight space, reward-out-of-recipe. |
| Q8 | SDK/CLI and web **in parallel**, on one spec and one runner, after the shared core. |
| Q-A | Texts stored **in the ledger** (zlib, same transaction as the reward). |
| Q-B | Audit mismatch: record and report; **quarantine after 3** mismatches (counts against both workers). Committed rewards never change. |
| Q-C | **One switch (flag day)**: r11 speaks only v3; devices not on r11 stop getting work (owner chose this against a transition release). |
| Q-D | Antithetic sampling **off by default**, chosen per experiment. |

The owner also allowed installing PEFT: `peft==0.21.2` is installed in the Conda env `heteroes-match` ONLY.

## 3. What is done (all CPU-tested; see the receipts)

| Area | Where | Key facts |
| --- | --- | --- |
| Recorded identities as tests | `runtime/tests/test_golden_identities.py`, fixture `runtime/tests/fixtures/golden-identities.json`, builder `runtime/scripts/build_golden_identities.py` | 8 recorded v1 recipes + 418 records from 234 ledgers; their RECORDED hashes, record texts and exact coefficients must still come out of the code. Recipe v2 identities frozen in `tests/study/test_recipe.py`. |
| One catalog | `runtime/src/heteroes/catalog.py` (stdlib only) | Pinned Qwen id/revision, workload names, decode engines. `backend/tests/test_catalog.py` rejects copies; `backend/runtime_sources.py` ships it with the Lab Server; `test_shared_runtime.py` checks the server subset's import closure. |
| Task seam | `heteroes.executor.evaluate_task`, `CandidateExecutor.last_completions` | One place evaluates a task; keeps the texts. |
| v3 documents | `runtime/src/heteroes/v3/documents.py` | Strict recipe + plan, every field explicit; `from_v1`/`from_v2` translation (read-only); mapping preview `docs/evidence/2026-10-19-extensibility-step1/v3-mapping.json`. NOTE: imports `heteroes.manifest` → NumPy; the backend venv has no NumPy. |
| Scorers | `runtime/src/heteroes/v3/scoring.py` (stdlib at import) | Declarative: `answer-line-last-number@1` (v2 rule), `last-integer@1` (arith16), `answer-line-integer@1` (cot), `regex@1`, `exact-string@1`, `choice-letter@1`; Python scorers by code hash; failures raise `ScorerError`, never 0. Rewards reproduce recorded arith16 rewards and today's `evaluate_cot` on recorded texts. |
| Antithetic | `runtime/src/heteroes/v3/antithetic.py` | (seed, ±1) pairs; perturb with `sign·σ` (perturb only requires a finite sigma); merge `c_k = float32((c⁺ − c⁻)/2)`, unique seeds to `apply_coefficients_`. No change to `noise/` or `es/`. |
| Subset | `model/schema.py` `select_parameters`, `SUBSET_SCHEMA_VERSION` | A declared sub-schema; `resolve_tensors` accepts it only as an ordered selection; full schemas still need an exact match. |
| LoRA | `runtime/src/heteroes/model/lora.py` | FP16 PEFT adapters = trainable schema; initial adapter is a hashed file; `export_peft` loads back with `PeftModel.from_pretrained`. |
| Ledger schema 6 | `runtime/src/heteroes/ledger/ledger.py` | `candidate.sign`, `UNIQUE(seed, sign)`, `completion` table (texts), `audit` + `record_audit` (quarantine at 3), `quarantine.reason`. **Schema-5 files are refused** ("replayed, not continued") and left untouched. |
| Record version 2 | `runtime/src/heteroes/generation_record.py` | `signs`, `coefficient_rule`, `update_inputs()`; version-1 records unchanged byte for byte. Coordinator and `replay.py` apply via `update_inputs()`. |
| Protocol v3 | `worker_api.py`, `worker.py`, `executor.py`, `coordinator.py` | `submit_result` with `completions` + `completions_sha256`; coordinator scores (`score=`), checks the attempt first; new error code `scorer_failed`; `ScoringFailed` stops a generation. Coordinator options `antithetic`, `coefficient_rule`, `score`. Executor `return_completions`. Without them every v1/v2 path is unchanged. |
| One-machine runs | `v3/data.py`, `v3/model.py`, `v3/run.py`, `v3/local.py`, `v3/__main__.py`, `heteroes/sdk.py` | Any safetensors model pinned by file hashes (no name list), datasets with any columns, `RecipeV3Run` adapter, `run_local`, `python -m heteroes.v3 run spec.json`, `ESConfig`/`ESTrainer`/`@reward`. Tested end to end with a tiny Qwen2 + tokenizer built offline (`runtime/tests/v3/tinylm.py`): re-scoring stored texts and hand replay of records give every committed reward and child hash. |

Small related changes: `study/evaluation.generate_rows` accepts a null system prompt and rows without `answer` (never
counted correct); `study/models.verify_files` shared by v2 and v3; descriptor `sign` (int, not in `candidate_id`).

## 4. Remaining plan (in order; each step = tests first, mutation check, a NEW evidence folder, logical commits)

1. **Product runner and agent on v3** (`runtime/src/heteroes/product/runner.py`, `product/agent.py`, `study/prepare.py`).
   Add `recipeVersion == 3`: build documents from the product config (reuse `v3/run.build_documents`), Ledger 6,
   `Coordinator(..., dataset, antithetic, coefficient_rule, score=make_scorer(...))` with **declarative scorers only**
   (`validate_plan(..., allow_python=False)`); worker side `CandidateExecutor(..., return_completions=True)` with
   `RecipeV3Run`; transfer the v3 dataset document and, for LoRA, the initial adapter file. Acceptance: the fixture lab
   (`scripts/check-all.sh` web/worker probes) runs a v3 experiment end to end on CPU; v1/v2 runs still pass.
2. **Validation/test evaluation for v3.** v2 had `study/tracker.py` (validation accuracy per interval); v3 has none yet.
   Reuse the run's declarative scorer on the validation split at intervals, on the coordinator. Acceptance: tracked metric
   in the run directory and the product timeline.
3. **Backend + web** (`backend/request_models.py`, `validation.py`, `study_registry.py`, `devices.py`, frontend wizard,
   Vietnamese i18n). Fields: weight space, antithetic, declarative scorer + config, coefficient rule, nullable system
   prompt, v3 dataset import with columns (`heteroes.v3.data` is stdlib-only; keep `v3/documents.py` OUT of the backend or
   make it NumPy-free; add any new shared module to `backend/runtime_sources.py` — the import-closure test will tell you).
   Device capability `recipeVersions: [3]`. Acceptance: browser fixture probes create and show a v3 run.
4. **Audit scheduling** (ADR-008 section 8): the coordinator picks ~5 % of committed candidates deterministically (hash of
   candidate id) and offers them as audit work to a DIFFERENT worker; the worker returns `completions_sha256`; call
   `Ledger.record_audit`. Show mismatches and audit quarantines in the UI. Acceptance: a fake worker with different texts
   is quarantined after 3 mismatches; rewards unchanged.
5. **r11 desktop** (owner + real machines): add `peft==0.21.2` with hashes to `desktop/worker/resources/requirements-*.txt`
   via `scripts/build-worker-profile.py` (never hand-edit generated profiles), v3 worker in the agent, **Windows v3
   acceptance on a real Windows machine** (Windows was never qualified for v2: `backend/policies.py:53`).
6. **Flag day** (owner decides the date): deploy server + r11 together; then remove the v1/v2 RUN paths (runner v1/v2
   branches, built-in workload selection, v1 validation). Keep `v3/documents.from_v1/from_v2`, the golden tests and the
   replay of old runs. Note: `Ledger` refuses schema-5 files, so any tool that must read old ledgers reads them with plain
   SQLite on a COPY (see gotchas).
7. **GPU acceptance and the first real experiments** (needs the owner's explicit GPU authorization and
   `HETEROES_GPU_ACCEPTANCE=1`; the 5070 Ti also runs the live lab): v3 on the pinned Qwen 0.5B, text equality across
   the 5070 Ti and the 1660S (contract §17), then a preregistered full-vs-LoRA comparison (repo practice: write the
   preregistration BEFORE the run).
8. **SDK polish**: examples, an entry point (`heteroes` command), Python scorer guidance (it runs in the coordinator's
   process: self-hosted only, no sandbox).

## 5. How to verify (CPU)

```bash
cd ~/projects/heteroes
scripts/check-all.sh docs/evidence/YYYY-MM-DD-name/checks          # 22 steps, ~5 min; must print ALL PASS
(cd runtime && CUDA_VISIBLE_DEVICES='' PYTHONPATH=src "$HOME/miniforge3/envs/heteroes-match/bin/python" -m pytest -q)
CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest backend/tests -q
python3 scripts/mutation-check.py --repo runtime --copy src --copy tests \
  --copy artifacts/probes --copy artifacts/regression --copy artifacts/experiments/2026-10-09-chunk128 \
  --env PYTHONPATH=src --env CUDA_VISIBLE_DEVICES= --scratch <scratch dir> \
  --test "$HOME/miniforge3/envs/heteroes-match/bin/python -m pytest -q -p no:cacheprovider <tests>" --mutants <file>
```

Last full run on this branch: runtime ~2,230+ passed / 100 skipped, backend 287 passed, check-all 22/22.

## 6. Gotchas learned the hard way

- **SQLite `mode=ro` still writes** `-shm`/`-wal` files on WAL ledgers. Never open ledgers under `runtime/artifacts/` or
  `docs/evidence/` directly: copy the file and its `-wal` to a temp dir first (`build_golden_identities.py` does this).
  `immutable=1` does not work: some recorded ledgers hold their rows only in a tracked WAL file.
- **Committed evidence folders are immutable**: later work gets a NEW folder, never an edit of an old README.
- **`pgrep -f`/`pkill -f` match your own shell command** (the pattern is in its text): wait on task notifications or PIDs.
- `ruff format` rewraps lines: a mutant's `old` text must be checked to occur exactly once AFTER formatting.
- A mutant that blocks a generation makes tests wait for the coordinator timeout: v3 tests pass `timeout_seconds=30`.
- `-1.0 in (1, -1)` is True in Python: type-check before value-check (descriptor `sign`).
- The backend venv has no NumPy: backend may import only stdlib runtime modules (`catalog`, `study/data`, `v3/data`,
  `v3/scoring`), and they must be listed in `backend/runtime_sources.py`.
- Markdown files are not covered by the Prettier check; do not reformat unrelated tables in `docs/HANDOFF.md`.
- The scoring tests read recorded texts from `runtime/artifacts/`: copy those paths into mutation scratch copies.

## 7. Working with the owner

Vietnamese, plain and short; explain from the basics with measured numbers; say what is inference and what the tests do
NOT show. The owner likes multiple-choice questions for decisions and decides; state a trade-off once, then follow. Commit
freely on the working branch in logical groups, **no Co-Authored-By or generated-by lines**, never push, never tag.
No GPU, SSH, lab-state or device-approval change without an explicit request (`3060-thao` is REVOKED).
