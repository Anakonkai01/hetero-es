# Extensibility step 0 — recorded identities, one catalog, one task seam

Baseline: `086c282` (branch `feat/extensibility-step0`). Step 0 of the owner-approved extensibility audit
(`~/.claude/plans/y-l-c-i-prompt-deep-cupcake.md`, outside the repository): groundwork that changes no recipe, workload,
record or dataset identity, so that the later Recipe v3 work (one format break, decided by the owner) has a safety net.

## What changed

- **Recorded identities as tests.** `runtime/scripts/build_golden_identities.py` collects, from `runtime/artifacts/` and
  `docs/evidence/`, every recipe document stored next to its recorded `recipe_hash` and every generation record of every
  ledger (`record_json`, `record_hash`, recipe hash of its generation): 8 distinct recipes (all four workloads) and 418
  distinct records from 234 ledgers, in `runtime/tests/fixtures/golden-identities.json`. The script computes no hash.
  `runtime/tests/test_golden_identities.py` checks that today's code gives every recorded recipe hash, workload hash,
  record hash and record text, and the exact recorded coefficients of every update (`verify_coefficients`, atol 0).
- **Recipe v2 frozen.** No v2 run is recorded in the repository, so `test_recipe_v2_identities_are_frozen` freezes the
  dataset/split hashes, recipe hash, batch indices, FP32 sigma and context hashes of the existing test recipe as computed
  by the code of 2026-10-19.
- **One catalog.** `runtime/src/heteroes/catalog.py` (standard library only) holds the pinned checkpoint, the workload names
  and the decode engines. `manifest.py`, `model/loading.py`, `study/models.py`, `study/prepare.py`,
  `product/run_supervisor.py` and the backend (`constants.py`, `devices.py`, `validation.py`, `templates.py`) import it
  instead of keeping copies. The Lab Server's runtime subset (`backend/runtime_sources.py`) now ships `catalog.py`.
  `backend/tests/test_catalog.py` rejects copies of these literals in production sources; a new test in
  `test_shared_runtime.py` checks that the server subset holds the whole runtime import closure of the backend.
- **One task seam.** `heteroes.executor.evaluate_task` is the single place where a recipe's task is evaluated (Recipe v2
  dataset rows, arith16, long workloads). It returns the reward and the texts it was computed from; the executor keeps them
  as `last_completions` (None after a failure). Reward values and patch points (`evaluate_model`, `get_workload`) are
  unchanged.

## Receipts

| Check | Result | File |
| --- | --- | --- |
| Runtime tests (CPU) | 2,119 passed, 100 skipped (2,110 before + 9 new) | `runtime.log` |
| Backend tests | 287 passed (283 before + 4 new) | `checks/backend-tests.log` |
| Full CPU product check (`scripts/check-all.sh`) | 22/22 PASS, including packaging and fixture browser/Electron probes | `check-all.log`, `checks/` |
| Runtime mutation check (scratch copies) | control passes; 13/13 mutants killed | `runtime-mutants.json`, `runtime-mutation.log` |
| Backend mutation check (scratch copies) | control passes; 6/6 mutants killed | `backend-mutants.json`, `backend-mutation.log` |

The runtime mutants cover hashing (canonical JSON, record text), coefficients (sample vs population std), a workload prompt,
the Recipe v2 sampler and cosine schedule, a catalog rename and every branch of `evaluate_task` / `last_completions`. The
backend mutants re-introduce each removed copy and break the server runtime subset.

## Incident during this step

The first fixture build opened recorded ledgers with SQLite `mode=ro`. On WAL ledgers this still rewrote 3 tracked `-shm`
files and created 432 untracked `-shm`/`-wal` files (216 empty WAL, 216 index files of 32 KB) between 16:37 and 16:39. The
tracked files were restored with `git checkout`, the created files were listed, checked to be only those files from that
window and removed; `git status` of `runtime/artifacts` and `docs/evidence` was empty afterwards. The script now reads a
temporary copy of each ledger and its WAL (`immutable=1` was tried and rejected: some ledgers keep their rows only in a
tracked WAL file). The rebuilt fixture is byte-identical to the first one.

## What this does NOT show

No GPU computation, no replay of a real run on a model, no Windows or packaged-app execution and no deployment. The golden
test proves that recorded identities still hash the same; it does not prove that today's code would generate the same texts
or rewards on a GPU. Recipe v2 values are frozen from current code, not from a recorded run. `last_completions` is not yet
sent anywhere: the worker protocol is unchanged.
