# B2 device, agent and scheduler layers

Baseline 96d662e7. Device HTTP adapters retain their original signatures/decorators; bearer header/path parsing remains
at the API boundary. Device authentication/permissions, enrollment, contribution and lifecycle decisions live in services.
Agent command/polling/scheduling mixins move with their original method signatures, relative imports and comments.
Nine Store methods delegate to device-state/scheduling services. The extraction accounts for 136 execute/write-boundary
calls across these components; statements live in per-domain repositories and BEGIN remains in the DB transaction helper.
Core constants were copied byte-identically; strict model bases and device contracts have normalized AST proofs.
Compatibility modules preserve old import/module identity during B2. Services use plain errors; HTTP mapping remains central.

Targeted regressions: agent mixins 76, core contracts 89 (the invocation listed device-self-control twice), device routes 92,
and remaining Store methods 80 passed. The first full backend run passed 479 tests. After nine additional guard regressions, the final full backend passed 488 tests, one existing Starlette dependency warning. All 62
original backend test files are byte-identical to 6ee47147. The 111 product routes/two mounts and 17 archive fixtures match.
Ruff lint/format pass.

Mutation control: control ok    | 97 passed, 1 warning in 15.54s. All 13 mutants killed: pairing expiry/single use, revoked auth, declared commands,
coordinator authorization, snapshot/event epoch and identity, verified pause, reserved GPU identity, strict layout,
offline ownership, admission hold and active reconciliation. The first two mutation invocations stopped at control
because they named nonexistent test files; they exercised zero mutants and are retained as failures. The final invocation
uses the existing model-qualification tests for strict scheduling plus nine new device-guard regressions. The initial valid run killed only 6/13: seven surviving guard removals exposed independent coverage gaps, fixed by these new tests without changing product behavior (FINDINGS-B B-005). Its complete log is retained. No invalid invocation is counted as a kill.

Intermediate failures are retained: a missed nested relative import was fixed before 76 agent regressions passed;
the Store move initially lost the ACTIVE/TERMINAL legacy imports, restored before the 80/full backend runs. The original
agent failure log contained ephemeral fixture bearer strings; only its redacted copy and hash/redaction record are archived.
The checked-in numerical runtime and live lab were untouched by this extraction.

## What this does NOT show

B2 still needs studies/qualification, storage and operations/app/remaining Store cleanup. This is isolated CPU/SQLite
regression, not PostgreSQL, OIDC, service replication, MinIO, packaged apps or GPU/Windows acceptance. Existing acceptance
mutant paths need relocation after shim removal in B9 before full B10 acceptance. B3–B10 and MiniCloud C remain unfinished.
