# B6 production S3/MinIO storage, dataset proxy and PostgreSQL restore

Baseline c44a2226; source hashes/patch/new-source identify this implementation. S3Backend restores the historical S3
single/multipart/inventory/conditional-publication behavior with lazy cloud SDK dependencies. No R2 confirmation,
HTTPS-only internal-container gate or classA/B request metering remains. Explicit nonempty credentials, SigV4/path
addressing, disabled environment proxies and distinct internal/device clients are tested. The device origin remains
numeric private/LAN/Tailscale; server HTTP supports internal Docker names. Shared byte quota counts all three explicit
buckets plus incomplete multipart parts. Recovery/model objects, datasets and metadata use their assigned buckets.

Actual worker-style signed HTTP PUT/multipart/download reaches the owned real MinIO release9e49d5e7a648 (build/source
provenance is in preceding B4 evidence). ETag-bound copy cannot publish an upload changed after verification. Expected
SHA is checked before SDK file publication, file bodies stream from disk, and staging is deleted only after successful
copy. Source NoSuchKey maps to FileNotFoundError. Abort is idempotent. Manifest publication and existing quota/auth
business policy stay in the services. Buckets are private, uniquely owned per test, and cleaned only by their fixtures.

Dataset import/upload/build and frozen device transfer now select the datasets view; model publication/qualification
keep recovery. Actual product API tests read objects through the matching bucket/private URL and restrict public URLs
to datasets. Public proxy capabilities bind method/key/expiry/size and actual bucket, survive replica restart with the
shared signing key, stream through private temporary files and clean up. Signed Content-Length and the64-MiB public
bound are checked independently. Actual response size is checked before public streaming. Reserved bulk API paths
return the private-transfer policy. Factory/lifecycle tests select S3 and close its clients after background workers.
S3 service union matches the original111 product pairs without overlap (API67/devices21/storage23).

Local disk and actual S3 run the same manifest/dedup/quota/invalid-content contract. Local metadata now accepts both
product.sqlite and product.pgdump (B-012); the initial pgdump whitelist failure is preserved. Production S3Backend also
uploads an actual PostgreSQL17 custom dump to its backup bucket, reads it back, downloads and restores a fresh PG DB.
Final receipt size54213 bytes, checksum recorded; sessions revoked, reservations retained and dispatch held. This is the
shipping adapter, complementing B4's earlier SDK test adapter. No private archive/SQL is included.

Final full MinIO-enabled SQLite627 / PostgreSQL652 passed, zero skips, two warnings (existing Starlette and intentional
weak-RSA test). PG target audit403 real PG Stores +48 explicit SQLite file-contract Stores; its owned fresh container
was removed. Both first full suites also passed, then final suites repeated after the independent header regression.
Focused contract suite31 passes, including real HTTP/local filesystem plus config/factory/route unit cases. Source
archive imports and lint/format pass; packaged-source smoke checks retain pinned Python/wheels/model.

Initial mutation: config8/9 killed and I/O20/21 killed. The private-origin survivor is equivalent: LocalBackend's signer
independently enforces the same private rule before S3 clients exist. A separate probe bypasses the first check and
confirms rejection by that second layer. It is recorded separately, not called a kill. The upload Content-Length
survivor was a test gap (B-013): the short-body case also failed at final byte count. A complete valid body with a wrong
header now isolates the early check. Final config8/8 (control10, five intentionally deselected real-I/O cases) and
actual PostgreSQL/MinIO I/O21/21 (control31) are killed:29 non-equivalent kills plus one explained equivalence. Initial
logs/input lists and final results remain. Mutation helpers remove receipt-output variables so they cannot overwrite
the accepted restore receipt.

## What this does NOT show

These are isolated CPU/API/disk/database/storage contracts. Device helpers use CPU fixture profiles; no GPU computation,
learning, deployed Keycloak, full MiniCloud cluster or multi-container failover is claimed. Frontend/desktop/runtime
source is unchanged from B5/Part A; the whole browser/Electron check-all was last accepted at B5. Fresh all-host/runtime,
full app packaging and final whole checks still belong to B10; private desktop Python dependency packaging to B9.
B7 metrics/logs, B8 course routes, B9 environment overlay and all C remain. The live lab and revoked public device are
untouched. Private resources, credentials/access identifiers, signing keys, signed capabilities, dumps, SQL and client
binaries are excluded. Original/redacted log hashes are recorded; diagnostic access identifiers are redacted along with
secrets. The independent owned development PG/MinIO containers remain available for subsequent B work; only test-owned
UUID buckets and the fresh matrix PG container were removed. The complete A->B->C goal remains active.
