# B8 opt-in course API

Baseline750575bd. Source hashes/patch/new source identify the implementation. HETEROES_COURSE_DEMO=1 enables hello,
secure, student and students-db only on api; default and all other roles omit them. The default111 product-route union
is unchanged. Course JWTs use the existing RS256/JWKS verifier with flask-app aud/azp, issuer and expiry checks. They
never create product users/sessions. A heteroes-web-only token, missing/wrong-scheme token, invalid signature/issuer or
expired token is rejected. JSON is read fresh with a1-MiB bound and required list. Data/DB errors have generic503 bodies.

Student SQL lives in its repository, uses PostgreSQL only, a fixed ordered SELECT and read-only transaction, with a
short-lived NullPool owner disposed after each request. Actual PG tests create a separate fresh DB and UUID-owned
NOLOGIN role, open a session with that role selected, prove SELECT succeeds and INSERT is denied, preserve ISO dates /
NULL and verify only students exists there. The API does not apply product schema or use its advisory write lock. The
owner test connection sets the read-only role explicitly; the deployment must supply its own SELECT-only login role.

Before implementation, an unchanged B7 scratch copy has11 red/9 passing course tests. Initial focused SQLite20/PG21
pass. Full actual-MinIO-enabled SQLite665/PG694, zero skips, two known warnings; PG audit441 PG +50 explicit SQLite
Stores and owned-container cleanup are recorded. After full-suite collection, one test-only independent oversized-file
case was added: final focused SQLite25/PG26 pass. Production source did not change between full suites and final focus.
Source-package isolated imports and lint/format pass. Existing tracked backend tests are unchanged at this milestone.

Initial mutation14/15 is retained. Removing the explicit size check still failed the initial huge string case because
its bounded prefix was malformed JSON. The added case is a complete valid list followed by excess whitespace: parsing
can succeed, so the size check must reject it. The final mutant name describes oversized valid-prefix acceptance, not
unbounded reading (the bounded read was never removed). Actual-PG final control26 passes and all15 mutants are killed.
No equivalence is claimed. Source and intermediate logs are retained with credential redaction/hashes and SHA manifest.

## What this does NOT show

This is generated-key HTTP/API and actual PostgreSQL role/data acceptance, not a deployed Keycloak/nginx course cluster
or the five real course records. The preceding B7 milestone passed all24 browser/Electron/check-all steps; B8 changes
only this disabled-by-default API feature and does not repeat those unchanged UI/runtime checks. Full final packaging,
three-host/GPU acceptance, B9-B10 and all C remain. No real lab/device approval was changed. Development PG/MinIO remain
owned and available; only test-owned databases/roles/buckets were cleaned. Credentials, private dumps/SQL and PG client
binaries are excluded. The complete A->B->C goal is unfinished.
