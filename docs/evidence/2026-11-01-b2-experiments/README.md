# B2 experiment, history, queue and Store state extraction

Baseline 07aba634. Experiment/history HTTP signatures and decorators are preserved; SSE/live slot handling and binary
StreamingResponse construction remain in the HTTP adapters. Business bodies and SQL move to separate modules.
Nine Store methods delegate to ExperimentStateService/WorkspaceStateService, with 16 SQL calls in repositories.
The moved UTC timestamp function has identical AST. Queue's business body, HTTP adapter and two queries move from
workspaces into experiments with identical AST. Explicit write starts now belong to db.transactions.

The archived pre-split inventory is copied byte-identically into a test fixture: all 111 product method/path pairs and
both static mounts match, without duplicates. Existing archive fixtures also match. All 62 original backend Python
test files remain byte-identical. Focused tests pass before and after the Store/queue move (67/68 checks).
New boundary cases prove recorded-child authorization with a positive owner read, queue visibility/cancellation/FIFO,
order-independent config identity, atomic rejection of non-finite JSON, immediate SQLite write ownership, empty versus
unknown event views, and held DRAFT submission/release.

Final full backend: 477 passed, one existing Starlette dependency warning. Mutation: final control 81 passed,
10/10 killed. The first mutation run's maintenance-hold guard survived its selected 80 tests (9/10 killed).
B-004 records this coverage gap; the added direct submission test kills it without changing production behavior.
Both intermediate and final logs are retained. AST proofs enumerate the allowed rewrites rather than inferring
behavioral equivalence from green tests alone.

## What this does NOT show

This completes this B2 domain slice, not the whole split. Store still owns scheduling/device/bootstrap code, and
other domains remain. It does not demonstrate PostgreSQL, process/service routing, Keycloak/OIDC, MinIO/S3, final
desktop packaging, new full B10 GPU acceptance, MiniCloud or deployment. Part A acceptance belongs to its own source.
