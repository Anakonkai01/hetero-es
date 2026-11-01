# B2 completed: DB, application composition and business isolation

Baseline 9817afb5. Store is a thin facade in services/store.py. SQLite bootstrap and connection ownership move into
DB; commit/rollback/close and the original RLock are preserved. Audit timestamp policy lives in a service, SQL in its
repository. The original DB method and bootstrap block have normalized AST proofs, including bootstrap comments.
Seven SQLite diagnostic queries and one bootstrap admission write move behind DB/repository owners. Doctor/bootstrap
business stay in services; CLI parsing belongs to apps, with unchanged CLI function ASTs. The diagnostic SQLite
connection arguments and caller-context lifetime are unchanged. Bootstrap's request contract keeps its class AST.

apps/factory.py composes HTTP and background work. AccessService owns fresh profile/workspace checks, visible runs,
authorization and capabilities. Original closure bodies are proved equal apart from explicit dependencies/plain errors.
API security owns the original Header/Depends signature. Workspace/operations/experiment services receive business
callbacks. SSE framing and static web remain in API, timeline projection in services, kernel writer lock in core, and
telemetry CLI in apps. Direct service imports avoid compatibility modules that also expose HTTP adapters. Legacy
namespaces remain only until B9, including doctor instrumentation and storage's explicit public instrumentation alias.

New complete-tree guards cover SQL ownership and API/service/core/storage dependencies. A clean subprocess imports
every service while actively rejecting FastAPI, Starlette and Torch: PASS. Initial red evidence caught the qualification
compatibility import pulling FastAPI into business code. Full post-split route contract remains 111 product method/path
pairs plus two mounts. All 62 original tests are byte-identical to 6ee47147; all 17 archive fixtures match. The entire
runtime tree is unchanged from the accepted Part A baseline. Ruff lint/format and recursive production runtime
import-closure checks pass. This does not claim the old flat packager has already been modernized; that is B9.

Independent SQL audit: all 278 unique expression ASTs match the pre-B2 baseline. Definitions change 358→350 only by
sharing BEGIN IMMEDIATE (9→2) and the session-revocation query (2→1). Generic forwarding and SQLite backup account for
two additional execution/snapshot call sites; all 352 are owned by db/repositories. A fresh isolated app's complete
catalog/column/index JSON equals B1 exactly: 37 tables,177 columns. These checks never inspect live lab state.

Targeted Store checks:42 passed; diagnostics/bootstrap:38; composition/access:50; complete layer/route guards:10.
Context checks protect commit/rollback with audit, use-after-scope rejection and fresh stored access despite a stale
supplied profile. Initial full suite passed501. Initial mutation control56 killed11/12; removing the visible-run owner
filter survived. A same-workspace participant/admin list regression closes this coverage gap (FINDINGS-B B-006), with
no product behavior change. Final whole backend:502 passed,one existing Starlette warning. Final mutation control57:
12/12 killed, covering DB durability/lifetime, fresh admission hold, schema/deployment gates, fresh access, list/detail
ownership, management-writer shutdown ordering/release and transitive HTTP import coupling.

Honest intermediate failures are retained. A generated import landed inside the doctor's multiline docstring; it was
moved after the parsed docstring. Factory imports initially confused a Registry service with its route installer and
AgentRuntime with its API adapter; the symbol-specific imports were fixed before the50/full runs. Earlier import/type
or test failures are not counted as mutation kills. Mutation copies backend and runtime/src; test_store_layers,
test_layer_imports,test_operations_layers,test_doctor,test_deployment,test_server,test_writer_lock,test_run_stream,
test_lab,test_experiment_layers run with backend Python,--tb=short,CUDA_VISIBLE_DEVICES='',PYTHONPATH=runtime/src:.
Full command: CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest -q --tb=short backend/tests.

## What this does NOT show

B2 layering is complete; B3–B10 remain. SQLite schema/HTTP/business behavior is covered here, not PostgreSQL portability,
service replication/leader election, OIDC, S3/MinIO, metrics/course routes, recursive packaged apps or final three-host
GPU acceptance. B3 will deliberately adapt tests for DB targeting and modernize the old flat runtime scan/doctor
instrumentation paths before B9's import-only shim-removal proof. MiniCloud C and deployment remain unfinished. No live
lab deployment/state change and no new numerical-runtime acceptance is claimed by this CPU evidence.
