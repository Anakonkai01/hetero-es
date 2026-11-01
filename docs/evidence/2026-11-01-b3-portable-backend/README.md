# B3 portable backend on SQLite and PostgreSQL 17

Baseline 8ba9d3f5 (B3 engine foundation); B2 completed at 7e6781ff. Store now uses SQLAlchemy Core for both dialects.
Repository source genuinely uses named SQL/explicit columns/portable upserts and deliberate JSON/order fragments;
there is no runtime DML dialect translator. Legacy SQLite migration/user_version=1 is retained. Additive ordering/version
metadata yields 38 tables/189 columns; actual logical schema receipts match types, PK and unique column sets. Username
and partial-index behavior, integer64/upload sizes, double timestamps, old ordering/bytes and restart bootstrap are tested.
Outer writers serialize before business reads; nested Store reads reuse their connection. PostgreSQL statement savepoints
preserve caught-conflict recovery and the root advisory lock. Dedicated SQLite snapshots avoid backing up an active writer.

Full SQLite: 528 passed, zero skips, one existing Starlette warning. Fresh full PostgreSQL 17.11 script invocation:
538 passed, zero skips, same warning. The extra ten cases explicitly exercise the second dialect. Audit: 334 real
PostgreSQL product Stores; 39 SQLite Stores in 35 explicitly marked local file/migration/corruption/backup contracts.
All ordinary product fixtures must select PostgreSQL; schemas are isolated per logical path/test, reopenings share state,
and no dummy SQLite file is created. The script owns a random-loopback PostgreSQL container and its receipt confirms
cleanup. The separate ongoing B3 development database is excluded from this cleanup and its private record is not archived.
A real two-process product race grants one device and physical GPU to exactly one assignment; the loser sees reservation.
This race is a CPU fixture without GPU computation.

Final schema/SQL mutation control: 14 passed, all 12 mutants killed (int32/float4 truncation, missing username constraint,
old/new insertion order, repeated bootstrap, empty IN, bind offset, JSON projection, public order leak, Core conflict
translation and aborted-root recovery). Integrated engine control 12 passed, all six mutants killed. Protocol mutations
were accepted separately in the foundation evidence. After full suites, additional precision/conflict assertions and the
restored intentional quoted-identifier lexer case passed the focused 22-case matrix and/or the final 14-case mutation
control. Production implementation did not change after those full-suite runs.

Failures remain visible: initial missing-module/API red tests; 11 first integration failures from old fixture INSERT
column counts and the removed sqlite3 backup method; a collection invocation missing pytest import; then 15 actual PG
failures caused by fixture double-quoted values and empty positive IN (). Explicit columns/dedicated backup API and portable
fixture quoting fix the former. IN (NULL) fixes the actual repository defect (FINDINGS-B B-007), with empty-query regressions.
The lexer test intentionally keeps quoted identifiers. Focused PG regressions then passed 64 cases. Failed/collection
runs are not accepted results; logs are archived in full with redaction hashes where fixture credentials/capabilities occur.

All assertion expressions and multiplicity per function in 70 baseline B2 test modules are preserved, with only SQL
literal quoting normalized for this proof. This does not prove entire test-body equality. Changes intentionally modernize
fixture SQL, explicit SQLite markers, snapshot API, recursive runtime scanning and doctor patch paths before B9's later
import-only comparison. All 18 archive fixtures match evidence byte-for-byte. Runtime source is unchanged since Part A.
Ruff lint/format and documentation formatting pass. Source hashes/patch/new files identify the implementation.

## What this does NOT show

B3 does not deploy or split services. Scheduler leadership/failover, durable diagnostics/cluster identity and PostgreSQL
pg_dump/restore remain B4. OIDC, MinIO, metrics/course routes, recursive desktop packaging, shim removal and full B10
GPU/Windows acceptance remain B4–B10. All MiniCloud C is unfinished. The live lab and its revoked device were untouched;
no new GPU/Windows or learning acceptance is claimed. The goal remains active.
