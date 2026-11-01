# B3 database engine and compatibility foundation

Baseline 7e6781ff. SQLAlchemy 2.0.55 Core owns transactions and rows/bindings for SQLite and psycopg 3.3.6.
SQLite claims BEGIN IMMEDIATE before yielding; PostgreSQL claims a root transaction advisory lock, outside statement
savepoints. Nested calls reuse one connection, a caught nested scope failure forces rollback, and handled integrity
errors do not poison the outer transaction. Bind values are never interpolated; bools retain integer storage and rows
preserve positional/named/dict access. psycopg is an optional cloud dependency; only the isolated backend venv changed.

Tests were added before implementation (missing-module red logs retained). Full SQLite backend: 520 passed, one existing
Starlette warning. Dedicated matrix against the owned random-loopback PostgreSQL 17.11 container: 24 passed (six SQLite
engine, six PostgreSQL engine and twelve protocol cases). Engine mutation control 12 passed, all six mutants killed;
protocol control twelve passed, all six mutants killed. The first engine mutation run was intentionally terminated:
a nested-connection mutant waited indefinitely for its own PostgreSQL advisory lock. The fixture now sets a 2s PostgreSQL
lock timeout; the mutant fails by ordinary test assertions/errors rather than a harness timeout. Its SQLite cases still
use the production 20s lock wait, and the completed mutant takes 45s. The interrupted run is not counted as acceptance.
Linter, format and isolated dependency consistency pass. Source hashes identify exactly this foundation.

## What this does NOT show

The product Store still uses the old SQLite owner. This is not a full PostgreSQL backend result. Schema, portable
repository SQL, Store integration, full PostgreSQL test targeting and the process race remain B3 work. No live-lab
state, GPUs, Windows acceptance, cloud deployment, OIDC or MinIO behavior was exercised. B3–B10 and all C remain open.
Private container credentials and environment values are excluded.
