# B2 storage layers and HTTP boundaries

Baseline af048af2 (recovery/local storage originals unchanged from 401cb4e1). Recovery business/permissions move to
services; 31 SQL calls move to a repository. Thirteen recovery HTTP adapters retain signatures/decorators. Ticket
services accept token/cookie values and return internal data; API adapters alone read requests, write cookies and emit
303 responses with no-referrer. Neither the cookie secret nor raw bearer is added to the public response or database.
Begin/Finish contracts retain their class ASTs. Business normalization and cookie/header split proofs are included.

Filesystem storage lives in storage/local_backend.py; HTTP streaming lives in api/local_storage.py. Business classes
keep their bodies except plain errors and the relocated core request contract import. API adapters translate errors
for both product apps and standalone FastAPI apps. Disk operations, cancellation shielding and thread-owned cleanup
remain as before. backend.local_storage aliases the same module so public monkeypatch/instrumentation paths still work.

Metadata publication/quota/retention live in services, one status SQL call in a repository, the exact original SQLite
snapshot block in db/backups.py, and the unchanged atomic directory-publication function in core/filesystem.py.

Expected-red plain-error/layer tests precede extraction. The first focused run finds the compatibility install alias
was removed as an unused renamed import; restoring it with explicit __all__ fixes all 38 focused checks. Three new
capability/ticket regressions pass: plain service errors, wrong/missing cookie without consuming the ticket, expired
ticket with valid cookie, and public JSON contains only downloadUrl. Final full backend: 492 passed, one existing
Starlette warning. All 62 original backend tests are byte-identical; all 17 archive fixtures and 111 product routes/two
mounts match. Ruff lint/format pass.

Mutation control: 28 passed; 17/17 mutants killed. Coverage includes HMAC/method/expiry, upload bounds/immutability,
event-loop responsiveness for write/cleanup, recovery checksum/quota/manifest publication, cookie possession/HttpOnly,
ticket expiry/session revocation, consistent snapshot and failed publication status. The first control failed because
its scratch copy omitted scripts/restore-metadata.py; zero mutants ran. The corrected invocation additionally copies
that script. Test command runs test_storage_layers, test_local_storage, test_local_storage_async, test_recovery_storage,
test_recovery_routes and test_metadata_restore with the backend Python, CUDA_VISIBLE_DEVICES='', PYTHONPATH=runtime/src:.
and --tb=short. Full command: CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest -q --tb=short backend/tests.

## What this does NOT show

B2 still needs operations/platform, application/core and remaining Store/diagnostic SQL cleanup. Database behavior is
SQLite; consistent backup must use a dedicated connection when B3 introduces write transactions, and OIDC tickets
need the B5 verified-expiry/account policy. No S3/MinIO or cloud claim is made here; B6 will exercise real MinIO. This is
not packaged-app, PostgreSQL, multi-service, GPU/Windows or MiniCloud acceptance. B3–B10 and C remain unfinished.
