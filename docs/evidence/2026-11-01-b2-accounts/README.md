# B2 accounts/auth extraction

First B2 domain after baseline 9d000271 (Part A main 6ee47147). HTTP adapters parse requests and build responses;
AccountService owns local sign-in, registration, profile/password and session policy. AccountsRepository owns SQL.
ServiceError is a plain error, translated by the application adapter. Store.profile delegates to the service.
Temporary root route import shims remain for unchanged clients/tests; other domains are still being extracted.

Tests were written before implementation: the red log records missing new modules. Final focused regression: 63 passed.
Full backend: 467 passed with one existing Starlette dependency warning. All 62 original Python test files match their
SHA-256 baseline; three new tests cover durable expiry/revocation, plain service errors and layer boundaries.
Mutation: control 63 passed; 7/7 mutants killed (expiry, password verification, approval, logout, password-session
revocation, login throttle and response headers). The initial invocation lacked its scratch parent; that failure is
retained, then the parent was created and the actual control/mutant suite passed.

## What this does NOT show

This is one completed B2 domain, not the full backend split. It does not prove PostgreSQL, OIDC, S3/MinIO, metrics,
service routing, rebuilt desktop packages, full B10 GPU acceptance, MiniCloud or deployment. Other domains and B3-B10
remain. The SQL is still SQLite at this stage, as specified by B2 before B3's named portable statements.
