# B2 studies, models and qualification layers

Baseline 401cb4e1; the two original domain files were unchanged from 96d662e7, used by the extraction helpers.
Six request contracts move to core with identical class ASTs. Registry/model-qualification business and plain errors
move into services; 13 HTTP adapters retain original signatures/decorators. The two repositories account for 31
execute/write-boundary calls; explicit BEGIN uses the DB helper. Normalized AST proofs preserve business bodies,
query expressions, SQL parameters and dependency forwarding. Old imports retain compatibility exports.

The new direct Registry test proves workspace/kind isolation and plain service errors. Its expected-red run fails
before extraction. The first focused run detects an unused DB-schema import in an API module, removed before the
96-test focused pass. The first full run detects the missing legacy dataset identity export (488 passed/one failed).
The export is restored; final full backend: 489 passed, one existing dependency warning. The CPU-only shared-runtime
identity/no-Torch test passes unchanged. All 62 original test files and 17 archive fixtures remain byte-identical;
the 111 product routes plus two mounts still match the archived inventory. Ruff lint/format pass.

Mutation control: 83 passed; all 15 mutants killed. Nine relocated qualification mutations protect decoder forwarding,
request validation, reference identity, pending-probe separation, durable job/command identity and status projection.
Six additional mutations cover workspace lookup, frozen epoch/object transfer grants, dataset-limit administration,
restore quarantine and live/unknown probe ownership. This run preceded the final compatibility-only dataset export;
the targeted implementations were unchanged, and the subsequent whole suite verifies the final export.

Commands: CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest -q --tb=short backend/tests (full).
Mutation driver: scripts/mutation-check.py --repo . --copy backend --copy runtime/src, env CUDA_VISIBLE_DEVICES='',
PYTHONPATH=runtime/src:.; test_study_layers/test_study/test_v3_study/test_large_datasets/test_model_qualification/
test_noise_engines with the backend interpreter and --tb=short. Mutants are included. Generation is followed by
ruff check --select F401 --fix on the new files, then ruff format. Frozen runtime and live lab were untouched.

## What this does NOT show

B2 still needs storage, operations/platform, application/core/remaining Store cleanup. This is isolated CPU/SQLite
regression, not PostgreSQL, OIDC, multiple services, S3/MinIO, packaging, GPU/Windows acceptance or MiniCloud. Existing
acceptance mutant paths will be relocated after B9 shim removal before B10. B3–B10 and C remain unfinished.
