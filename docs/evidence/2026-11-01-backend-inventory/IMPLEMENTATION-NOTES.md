# Preparation notes for B (not an implemented result)

Use the approved plan as authority. Start feat/cloud-services only after A is green and main fast-forwards.
The snapshots in this directory were made on isolated throwaway state; they do not describe live lab contents.

## B2 implementation constraints

- Preserve existing backend tests unchanged during domain extraction. Accounts/auth first, then workspaces,
  experiments/history/queue, templates/notifications, devices/agent modules, studies/qualification, storage, operations.
- Put request parsing/dependency declarations/HTTP responses in api; business operations in services; every SQL statement
  in per-domain repositories; schema/transactions in db; common policy/config/security in core; factories in apps.
- Old module aliases must preserve monkeypatch targets as well as imported names while tests remain unchanged.
  A temporary sys.modules alias can preserve module identity better than star re-exports that omit private names.
- Avoid replacing a flat monolith with a flat folder of renamed route installers: routers really must become thin,
  Store must become a facade, and SQL must leave services/API.
- Only 9 of 358 SQL-call expressions are dynamic. sql-statements-before.json identifies all of them and their scopes.
  Most statement/parameter transformations can be mechanical; preserve evaluation order and named bindings.
- Explicit legacy ordering is required for users, devices, assignments, assignment_members, study_assets, study_uploads,
  workspaces, join_requests, experiments and model_probe_jobs. Preserve old insertion order during SQLite migration.
  Telemetry pruning can use its composite key rather than hidden rowid. Do not substitute PostgreSQL ctid.
- The product still has nested Store.db() calls (profile/get inside an open write). Cross-process transaction locking must
  not deadlock by acquiring the PostgreSQL lab advisory lock on a second connection in the same thread.
- Existing migration tests require SQLite user_version=1; additive tables/columns follow the existing extras migration
  pattern. Any version change must preserve valid desktop/lab migration behavior and be justified with real old DB tests.
- Full backend tests under HETEROES_TEST_DATABASE_URL must exercise actual product operations on PostgreSQL. SQLite-only
  database corruption/migration tests still test SQLite explicitly; do not fake PostgreSQL coverage by ignoring the env.

## B4/B5/B7 constraints

- Product route union: API 67 + devices 21 + storage 23 = baseline 111 method/path pairs, plus 2 static mounts.
  Health/readiness/metrics are deliberately shared operational routes; keep that distinction explicit in equality tests.
- Persist dispatcher diagnostics; API replicas cannot treat an empty local Store.last_error cache as scheduler health.
- Scheduler leader ownership is a dedicated PostgreSQL session advisory lock; business writes use transaction locks.
- Keycloak cloud mode owns password/registration throttles. Device token authentication remains unchanged. Local all mode
  keeps the existing auth behavior. JWT users map to kc:sub; role lab-admin affects platform administration, other users
  remain pending approval. Avoid resurrecting revoked/suspended local account status on every token request.
- JWKS client needs bounded network/time/body size, no redirect, strict RS256 keys, issuer, aud OR azp, exp/nbf leeway 30s,
  cache and controlled refresh for a new kid. Do not let attacker-selected kids cause an unbounded fetch loop.
- HTTP metrics/logs use route patterns. Never log raw request path/query, auth headers, request bodies, credentials,
  signed capabilities, access tokens, full config or exception messages that may contain them.
- Existing frontend access tokens are already handled by api/client and SessionProvider. Add oidc-client-ts with in-memory
  user/token storage, PKCE callback and renewal/end-session; local browser contracts must continue to pass.
- /lab/ mounting needs Vite base and BrowserRouter basename; API calls already use absolute /api/v1 paths.

## B6/B9 constraints

- Restore S3Backend from 8226f32b^:backend/cloud_storage.py as required, then remove R2-specific accounting/confirmation.
- Internal MinIO management endpoint and private device presigning endpoint are separate. Bulk transfers stay private.
- New backend use of heteroes.http_safety requires adding it to the CPU shared runtime subset shipped in server archives.
- scripts/build-server-profile.py currently uses backend/*.py: change to recursive source inclusion excluding tests.
  Validate generated server/worker packages and source archives, not only Python imports in the working tree.
- B9 import-only test changes need a real diff proof. Keep public desktop CLI entrypoints (server/doctor) intentionally
  thin where required; do not break external command strings merely to eliminate all root .py files.

## Primary references checked 2026-11-01

- SQLAlchemy SQLite transaction control: https://docs.sqlalchemy.org/en/20/dialects/sqlite.html
- SQLAlchemy named text bindings/transactions: https://docs.sqlalchemy.org/en/20/tutorial/dbapi_transactions.html
- SQLAlchemy connection/pool behavior: https://docs.sqlalchemy.org/en/20/core/connections.html
- PyJWT current API/JWKS cache: https://pyjwt.readthedocs.io/en/latest/api.html
- Keycloak hostname/backchannel: https://www.keycloak.org/server/hostname
- Keycloak management health/metrics paths: https://www.keycloak.org/server/management-interface

## Course source

The supplied original DOCX was extracted to ../course-requirements.txt. It names nine server categories; category 8 is
Logging/Visualization (Grafana/Loki). Its examples already add node-exporter as an extra container. The approved plan
intentionally adds replicas and HeteroES services; report nine categories while accurately listing every real container.
Do not execute destructive cleanup examples or reuse the document's demo passwords in deployment.

## Additional transaction/auth/logging pitfalls to verify during implementation

- Existing SQLite integer columns receive Python bool values. Normalize boolean binds to 0/1 for PostgreSQL integer
  parity, rather than silently changing the PostgreSQL column types and breaking schema equality.
- Replace the nine product BEGIN IMMEDIATE calls when transaction ownership moves into Database. Nested BEGIN on an
  already-owned transaction fails. Legacy SQLite migration initialization still needs its own explicit behavior.
- sqlite3.Connection.backup can wait indefinitely on its own active write transaction. Metadata backup needs a dedicated
  consistent read/backup path; do not call it from a newly unconditional BEGIN IMMEDIATE source context.
- Keep database-internal order columns out of public JSON. Add explicit INSERT column lists before adding columns to old
  tables, preserving legacy ordinal values and future insertion order. Do not rely on PostgreSQL physical tuple order.
- OIDC exp must be required; nbf is verified with the 30s leeway when present (ordinary Keycloak tokens may omit nbf).
  Never promote suspended/rejected users merely because they presented another valid token. Namespace identity by sub,
  never auto-link an existing local user by preferred_username. Handle username collisions explicitly.
- Unknown kid must cause a controlled refresh without an attacker causing arbitrary network fetch volume. Cache-negative
  misses and/or bound refresh rate while allowing the first actual rotation to refresh immediately; test both cases.
- PKCE state/verifier must survive the browser redirect; access/refresh tokens remain in the in-memory user store.
  Erase the callback code from the visible URL after processing. Gate local password/profile-password UI in OIDC mode.
- Gateway default combined access logs include query strings and signed path capabilities. Use safe route labels or
  disable logging for capability/auth paths, so centralized Loki logs do not capture OAuth codes or signed URLs.

## FastAPI route inventory detail

Current FastAPI includes lazy/included router objects without a direct path. The baseline walker recursively descends
such objects before collecting APIRoute and Mount entries. B4 cannot assume every app.routes element has .path or can
be filtered as a flat list. Preserve dependency factories needed by storage even when the devices HTTP routes are not
installed on that service. A registration facade or explicitly owned routers can filter product routes at registration.
Framework documentation routes should have one explicit owner or be disabled in production; common health/ready/metrics
are the three deliberately shared operational routes, not product-route duplication.

## PostgreSQL primary-source checks (2026-11-01)

Source: https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS

Session and transaction advisory requests with the same key conflict. Use distinct scheduler-leader and lab-write
keys. Repeated acquisition on one session requires corresponding unlocks; do not reacquire each leader heartbeat.
A session lock outlives rollback, so returning a connection to a pool is not a release strategy. Explicitly release
leadership and close/invalidate its physical session; test graceful shutdown as well as process death. Keep the lab
transaction lock outside any savepoint whose rollback must not drop serialization.

Source: https://www.psycopg.org/psycopg3/docs/basic/transactions.html

A failed PostgreSQL statement leaves its transaction aborted until rollback. Review every caught IntegrityError path:
use portable ON CONFLICT or a savepoint where business logic continues in the same transaction. Test commit/rollback,
nested calls and error recovery against a real PostgreSQL server. Long-lived leader heartbeats must not leave an
unintended idle transaction open; use deliberate connection/transaction ownership.

## Existing test compatibility points verified by source inspection

- test_v3_study.py calls templates.clean_config directly and requires HTTPException for invalid options. Keep this
  established in-process exception contract while moving validation; do not alter assertions just to make layering pass.
  Semantic core exceptions may preserve the legacy exception base while API adapters own response serialization.
- Only two backend tests use string monkeypatch targets into an old flat module:
  backend.local_storage.os.fsync and backend.local_storage.time.time. All other inspected targets use imported objects.
  B9 requires import-only test edits, so preserve these patch points through a deliberate package API attribute if the
  old physical module is removed. A lazy backend.__getattr__ export avoids importing FastAPI/storage when stdlib-only
  packaging tools import backend. Document any retained public namespace alias; remove the obsolete physical shims.
- When extracting local storage HTTP routes, preserve cancellation shielding, descriptor/partial-file cleanup and the
  exact same shared os/time module objects targeted by those tests. Do not weaken async disconnect/cancellation tests.

## Split-instance configuration detail

Existing app_from_config assigns runtime.server_instance_id from private config. API replicas/devices/storage must
advertise the same stable cluster identity, not generate a new server ID per container. In PostgreSQL mode persist or
validate this identity transactionally in shared settings; preserve the existing configured identity in local all mode.
Test identical health/enrollment identity across two API instances, and stable identity after restart. Separate the
coordinator container's bind workerHost/workerPort from its advertised computeUrl as already supported by AgentManager.

## Route/packaging details to verify

- Register /healthz,/readyz,/metrics before the web catch-all; adding them after /{route:path} can return SPA HTML instead
  of diagnostics. Exercise the all+web configuration as well as headless service factories.
- Compare product-route ownership under matching feature configurations (local storage and S3/cloud). Export the full
  contract without querying the live lab or requiring a real production DB just to generate nginx configuration.
- Recursive server packaging must consider the PostgreSQL schema SQL resource where needed, not only Python modules.
  Keep optional psycopg/JWT/S3 imports lazy for desktop local mode, and validate packaged behavior with actual artifacts.

## Dependency / test targeting follow-up (2026-11-01 03:58)

Official SQLAlchemy 2.0 documentation now identifies maintenance release 2.0.55 (2026-10-16); 2.1 is the current
series. Pin a verified available 2.x release deliberately, matching its own docs, rather than assuming older versions.
PyJWT stable API is 2.15.1. Dependencies SQLAlchemy/psycopg/PyJWT/cryptography/prometheus-client are not currently in
.venv-backend; boto3 1.43.111 is present. Do not change the active acceptance environment while the matrix runs.

Backend tests contain explicit SQLite file-format, migration/corruption, desktop bootstrap and metadata restore
contracts. These must keep testing actual SQLite even during the PostgreSQL invocation; document explicit targeting,
then ensure ordinary product fixtures and every portable business operation really use PostgreSQL. In particular,
test_api.test_credentials_are_hashed_and_no_lease_secrets_in_product reads Store.path as file bytes and metadata restore
calls connection.backup. Do not create dummy SQLite files or silently ignore the PostgreSQL env to make these pass.
Adapt the test environment explicitly in B3; B2 still requires the original backend tests unchanged. B9's import-only
proof must compare the before/after shim-removal step, not erase legitimate database coverage improvements from B3.

Only two tests reopen via Store(store.path, {}, runtime); preserve a stable database target across facade instances.
Multi-instance tests must share their PostgreSQL schema, while independent pytest tmp_path labs remain isolated.
Bootstrap migration tests seed an existing legacy SQLite file before constructing Store, which must remain SQLite.

## Frontend OIDC source inspection / primary references (2026-11-01 04:05)

Current api/client.ts initializes its token from sessionStorage and setAccessToken writes it back. Existing local browser
checks intentionally inspect heteroes.access-token; keep that local behavior, but choose memory-only persistence before
any cloud session API request. Merely configuring oidc-client-ts's userStore to memory is insufficient if api/client.ts
still writes the JWT to sessionStorage. Clear legacy stored credentials when switching into cloud mode. Workspace
selection can remain in sessionStorage (it is not a credential). Test token absence in both localStorage/sessionStorage
through sign-in and automatic renewal in OIDC mode.

Primary library docs: https://authts.github.io/oidc-client-ts/ and classes/{UserManager,WebStorageStateStore,
InMemoryWebStorage}.html. Use WebStorageStateStore({store:new InMemoryWebStorage()}) for user/token state;
use sessionStorage for transient PKCE/state across the authorization redirect. signinRedirectCallback processes normal
redirects, signinSilentCallback notifies the renewal parent, signinSilent renews using refresh token or iframe, and
signoutRedirect uses the end-session endpoint. Do not enable console logging of OIDC library state.

Read runtime /config.json before mounting SessionProvider/getSession; retain local mode and its fixtures. Validate an
explicit cloud config; do not turn malformed cloud config silently into local auth. Preserve a local default config for
desktop. BrowserRouter basename must agree with Vite base /lab/. Callback routes must be outside RequireSession. Handle
a silent callback before starting an ordinary React session tree, erase code/state from the visible URL, and keep a
safe relative return destination. A hard refresh discards memory-only tokens; use Keycloak SSO/session renewal rather
than persisting tokens to survive it. Remove local register/password/revoke-other-sessions UI in OIDC mode.

## Restored S3 compatibility gaps found by read-only inspection (B6)

The required historical S3Backend is smaller than today's LocalBackend interface. Do not copy it and declare S3 done:
- Dataset upload-plan passes public_base; historical S3Backend has no such argument.
- Dataset build uses backend.root for bounded temporary work, put_file for split files, and get/delete/put for objects.
- Device study-transfer calls public_study_url for the approved small public dataset fallback.
- Public upload/study capability routes must remain in the route contract and enforce the same size/method/expiry rules
  in S3 mode. Large recovery/model presigned transfers must use the private device endpoint, not the public gateway.
- Preserve cancellation shielding and exact length/hash checks when public dataset uploads stage locally then publish
  to MinIO. Do not serve an incomplete staged file as a committed object.
- A three-bucket cloud deployment needs an explicit storage ownership choice: recovery objects, study/dataset objects,
  metadata backups. Keys are currently content-addressed objects/<sha> in both recovery and study flows, so inferring
  the bucket from that prefix alone cannot distinguish them. An explicit study storage facade/backend and separate
  backup prefix/bucket is cleaner; keep local mode's existing shared storage behavior and old paths unchanged.
- Internal S3 endpoint may be Docker DNS/http; device presigning endpoint must be validated numeric private/Tailscale
  origin. Use separate clients so SigV4 Host and endpoint remain correct, path-style addressing for MinIO. Real tests
  must actually upload/download with the device URL, not just assert that a URL string was generated.

Existing LocalBackend caps public study/upload at 64 MiB; Public study GET grants are five minutes, private GET grants
60 seconds, upload grants 900 seconds. Historical S3 multipart part size is 64 MiB. Keep explicit body caps in nginx and
HTTP adapters and avoid logging signed capabilities/query strings.

## SQL type / compatibility details for B3

- SQLite INTEGER is signed 64-bit; PostgreSQL INTEGER is only 32-bit. Use PostgreSQL BIGINT for matching logical
  integer fields, including object sizes (valid uploads can exceed 2 GiB), sequence IDs and explicit insertion order.
- SQLite REAL stores double precision; PostgreSQL REAL is float4. Use DOUBLE PRECISION for times/telemetry sampling
  and other real-valued columns. Do not silently reduce timestamp precision in the Postgres schema.
- SQLAlchemy 2 Row is not a sqlite3.Row drop-in: existing code uses both row[0], row['name'] and dict(row). Return a
  deliberate compatibility row/result interface or update repository outputs; do not discover this only in PG tests.
- SQLite executescript commits an existing transaction. A Database-owned BEGIN IMMEDIATE must not be undone midway
  through schema initialization by a raw sqlite3 executescript call. Keep migration transaction ownership explicit.
- Production repository SQL must be named/portable after B3; do not rely on a generic runtime SQL translator instead
  of actually replacing SQLite-specific statements. Test fixtures containing direct SQL need explicit portable SQL
  or deliberate SQLite-only targeting in B3 (B2 originals still unchanged).

Account extraction: test_throttle.py replaces app.state.login_failures/login_failures_by_address/registrations after
create_app, before requests. Resolve the current counters per request when handing plain policy inputs to the service;
do not capture the original counter objects in a service constructor and break clock/throttling compatibility.
