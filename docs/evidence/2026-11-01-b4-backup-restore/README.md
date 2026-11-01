# B4 PostgreSQL metadata backup, actual MinIO restore and complete local checks

Baseline 3cadc1ca, working source identified by hashes/patch/new-source. PostgreSQL17 custom archives carry schema,
format, size and SHA. Credentials remain in a private libpq environment. Client major17 is checked; source tools come
from the owned official PostgreSQL17.11 image without host package/Conda changes. Upload and read-back precede manifest
publication; failure retains local data/PENDING. Retention follows payload keys across SQLite/PostgreSQL points.

The actual MinIO heteroes-backups bucket receives a real PostgreSQL dump. Both the direct11-test drill and final full
matrix download it and restore into fresh PostgreSQL databases. Restore checks empty target, checksum and agent/schema
identity, then atomically restores and revokes sessions/download tickets, holds dispatch and preserves reservations.
An invalid identity rolls back to empty. Actual remote object corruption prevents manifest publication and keeps local
data. B-009's pgx schema wildcard defect has a preserved failing regression and exact-prefix fix. Backup16/16 mutants
are killed (control12 passed), including private stderr/ambient libpq and independent quarantine guards.

The first check-all-final invocation exited0/ALL PASS despite five failed fixture startups; REJECT it as acceptance.
It skipped web-live/experiments/audit-outcomes/showcase/pages. Old implicit seed INSERTs broke after additive columns,
and startup failure never reached failed[]. Red regressions, explicit columns and mandatory failure accounting fix
B-010. Startup diagnostics now live under output rather than deleted WORK. The original temporary startup logs were
already lost: fixture-log-preservation records zero recovered; the failure-accounting reproduction is a unit test,
not substitute browser acceptance. The replacement check-all-accepted executes all24 actual steps successfully and
retains all seven startup logs. Fixture mutation4/4 is killed (control2 passed).

Final full SQLite548 / PostgreSQL572 passed, zero skips, one existing Starlette warning. The PostgreSQL target audit
is371 actual PG Stores and48 explicit SQLite file-contract Stores; its ephemeral container was removed. CPU check-all
also reports3324 runtime passed/1045 intentional CUDA-hidden skips, all browser/Electron contracts, lint, format, types,
i18n and source imports. Linux build-apps --check built both unpacked apps and checked shared JavaScript module imports;
receipt parent commit identifies the baseline, while source hashes identify the modified working tree.

The old official MinIO image was unavailable (failed pull log retained). Built official source release
RELEASE.2025-10-15T17-29-55Z, commit9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a. minio-start.json records source archive
SHA, Dockerfile SHA, image ID, runtime commit and health200. Docker build logs record resolved base digests:
golang1.24.8-alpine3.22 sha256:3d78beb141d98f42337f1252ecf2a5f20374109929a4c3f6817f9e4179cc0ae5;
alpine3.22 sha256:2e0b81d60597f449baa56dc25d355367869d2dca4cd57e866f1e2b52af3eb55f.
Recipe is included; source archive URL is https://codeload.github.com/minio/minio/tar.gz/9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a.
No unverified mirror was used. B4 is complete together with the preceding service/scheduler core evidence.

## What this does NOT show

The MinIO SDK adapter is a real-I/O test adapter, not production S3/factory integration (B6). Private dumps, SQL, resource
records/credentials, extracted client binaries, image layers and unpacked apps are excluded. A mutation invocation once
overwrote a scratch drill receipt; that receipt is rejected/excluded, the helper now removes receipt output during
mutation, and final direct/full receipts come from unmodified runs. Logs are redacted with original/archive hashes.
Linux app checks do not install/validate private packaged Python dependencies (B9/B10), or prove Windows/GPU acceptance.
The numerical runtime is unchanged since Part A. No live lab deployment/state change, public revoked-device change,
production cloud cluster, OIDC acceptance or learning is claimed. B5–B10 and all C remain; the entire goal is active.
Owned development PG/MinIO containers stay available for subsequent B steps; only the fresh matrix container was removed.
