# B2 operations, inventory, policy and core layers

Baseline 9d7d481b. Operations/inventory business and 13 HTTP adapters are separated with original HTTP signatures and
decorators. Thirteen SQL calls move to two repositories. Shared policy functions move to services with five more SQL
calls in a policy repository and plain service errors. Configuration validation moves with normalized body AST equality;
an explicit API wrapper keeps the original direct-call HTTPException contract. Existing domains import shared policy
business functions directly. RuntimeRejected retains its class AST in core/errors.

Config, addresses, observation contracts and throttle modules copy byte-identically into core. Request-contract class
ASTs remain unchanged; Strict imports the core base directly. Root modules retain compatibility namespaces/exports.
The first generic extraction exposed a service-factory/endpoint name collision and a generator variable overwritten by
internal endpoint-call rewriting; both were fixed before the focused 135-test pass. Four new authorization/validation/
maintenance checks pass, including success clearing old flags and rejection of unknown imported queued workers.

Two full runs preserve honest failures from the old flat-only runtime dependency scanner's catalog.py premise. The
request_models shim retains its original catalog public imports, which are already present in its aliased core module.
Final full backend: 496 passed, one existing Starlette warning. All 62 original tests remain byte-identical, all 17 archive
fixtures match, and the 111 product routes/two mounts remain intact. Ruff lint/format pass.

A separate scratch execution strengthens the original dependency-closure assertions with recursive production backend
traversal, excludes tests as packaging will, and resolves a bare package import. The original test file is never edited;
its SHA256 and final PASS are recorded. The first recursive attempt included tests and hit the old bare-package resolver,
retained in recursive-runtime-closure.log. This is source dependency closure, not a packaged-app import probe. Promote
the stronger scanner before B9 shim removal during post-B2 test adaptation; preserve B9's import-only test-diff proof.

Mutation control: 48 passed; 12/12 mutants killed. Cases protect self-access/session controls, suspension effects,
maintenance worker validation/hold/stale flags, public/private address separation, disabled workers, unknown process
state, physical/probe GPU ownership, required coordinator validation and legacy HTTP error status. Only compatibility
catalog imports were added after that run; mutation target implementations stayed unchanged and final whole-suite
regression verifies the export. Test command uses test_operations_layers, test_operations, test_self_administration,
test_lab, test_api, test_policies and test_private_address; CUDA_VISIBLE_DEVICES='', PYTHONPATH=runtime/src:., backend
Python and --tb=short. Full command: CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest -q --tb=short backend/tests.

## What this does NOT show

B2 remains unfinished: application composition/access callbacks, Store DB initialization/transactions/audit and SQLite
operational diagnostics still need their final ownership cleanup. This does not prove PostgreSQL, multi-service state,
OIDC, MinIO, recursive packaged apps, final GPU/Windows acceptance, MiniCloud or deployment. B3–B10 and C remain required.
