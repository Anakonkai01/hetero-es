# B5 OIDC verification, identity authorization and browser Code + PKCE

Baseline cbd6d904; source hashes/patch/new-source identify the modified tree. Local authentication remains default.
Explicit OIDC selects RS256, exact issuer, required exp/sub, optional nbf and30-second clock skew; aud or azp selects
heteroes-web. Internal JWKS uses shared no-redirect/no-proxy HTTP,5-second timeout,256KiB read bound, max32 suitable
RSA signing keys (>=2048 bits). Cache TTL300 seconds; first unknown rotation refreshes immediately, later unknowns and
failed fetch retries are bounded5 seconds, negative IDs are bounded64/30seconds. Invalid credentials return a safe
message without bearer/library/network data. The shared CPU runtime subset now includes http_safety.py.

Subject identity kc:<sub> never links by username; collisions return409. Ordinary accounts start PENDING, new realm
lab-admin accounts bootstrap ACTIVE/platform admin/default-lab membership. Reauthentication retains durable approval
and derives role only for ACTIVE accounts. Restricted accounts never revive. Cloud mode seeds no local passwords and
local auth/password endpoints give guided404; the OIDC password sentinel cannot authenticate through the local service.
Device enrollment/auth remains separate. External session revocation points to the provider instead of false success.
Download tickets retain only a digest and cannot outlive JWT expiry; they recheck durable account/membership/ownership,
remain single-use, and presented-token logout invalidates them. No raw JWT/local session row is persisted for OIDC.

Web config is loaded before session queries. The actual oidc-client-ts3.5.0 library uses Code+PKCE, memory-only user
storage and sessionStorage only for unfinished PKCE state. Callback queries are erased on success/failure; token events
refresh the API/query state. Runtime basename supports /lab; the asset build base is configurable. Local password UI
is replaced in OIDC mode and provider end-session logout is used. Dependencies are optional cloud Python pins;
an actual isolated local app+HTTP probe succeeds with jwt/cryptography/psycopg/boto3/botocore/torch imports forbidden.

Final full SQLite596 / real PostgreSQL17.11 620 passed, zero skips. Two warnings are the existing Starlette deprecation
and the deliberately generated weak-RSA rejection test. PG audit388 PostgreSQL Stores +48 explicit SQLite contracts;
the fresh owned matrix container was removed. The first PG full run had2 failures: an nbf test value was computed at
collection and became stale during the long suite, and the package closure lacked http_safety.py. Values now compute at
execution and the dependency is shipped; old assertions are preserved. Corrected focused closure/time checks51 pass.
Final actual-PG mutation25/25 (control48) and frontend/harness mutation11/11 (control6 Node tests) are killed.

The final Chromium protocol fixture receipt proves6 contracts: external UI/no local password, actual Code+PKCE and
clean /lab callback, memory-only access/refresh tokens, actual refresh grant, SSO recovery on reload, provider logout.
Safe counters are codeGrants2, refreshGrants1, logouts1, pkceVerifiedtrue. Screenshot was visually inspected and shows
an authenticated fixture account/workspace. No HAR, token, OAuth-code or private-state capture is included.

Intermediate browser failures are retained. The first probes waited for a logout button inside a closed account menu;
the harness now observes the visible account summary and opens the menu for logout. browser-third printed PASS with
refreshGrants0: REJECT it as renewal evidence (B-011). A Node poll now explicitly awaits HTTP counter advancement and
asserts it in the final receipt; zero/missing counters have independent regression/mutation protection. A later reload
failure came from the test injecting an old local token on every iframe/about:blank navigation; one-shot seeding fixes
the test without weakening the storage assertions. browser-counter-accepted proves renewal before adding reload; the
canonical six-contract receipt is browser-reload-accepted. No early failure is hidden or promoted to final acceptance.

The first check-all reports a Python-format failure during the test timestamp correction and exits1; retain it as a
failed invocation. The replacement check-all-accepted passes all24 actual steps: runtime3324 passed/1045 intentional
CUDA-hidden skips, backend596, local browser/Electron fixtures, imports, lint/format, types and i18n. B5 is complete.

## What this does NOT show

The OIDC HTTP/browser provider is a generated-key protocol fixture, not a deployed Keycloak realm. Real Keycloak,
MinIO production storage integration, full metrics, multi-container HA and GPU/Windows acceptance remain B6–B10/C.
Offline JWT verification observes provider revocation/role changes only through token expiry/refresh; durable product
suspension and membership checks remain immediate. No live lab deployment/state or revoked-device approval changed.
Private resource records, passwords, JWTs, RSA keys, dumps and extracted client binaries are excluded. Logs have original
and redacted hashes. Source-package smoke checks do not prove installed private desktop Python dependencies (B9/B10).
The numerical runtime remains unchanged since Part A; no learning claim is made. The full A->B->C goal remains active.
