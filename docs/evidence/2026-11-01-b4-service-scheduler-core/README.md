# B4 service partition and active/standby scheduler core

Baseline 1e81c585. Five role factories/CLI entrypoints share one codebase. An explicit registration facade preserves
unregistered dependency factories while partitioning handlers before registration. Four web/local-storage feature
profiles prove disjoint union equality. Full contract: 111 product pairs (API67/devices21/storage23), two API mounts,
three separately shared operational routes. The machine-readable exporter reads only isolated throwaway state.
Operational routes precede the SPA. API/devices start neither dispatch nor metadata backup; storage owns the latter.
The API keeps the legacy GET catch-all, so an unknown POST may correctly report 405; this initial test mismatch is
retained. All original product method/path assertions remain; only explicit operational routes are excluded from their
baseline comparison. Nineteen archive fixtures match immutable evidence.

Production split roles require PostgreSQL; two API factories share state without a local writer descriptor. All+SQLite
retains its kernel writer/shutdown contract (those tests now explicitly select SQLite). Initial role/database environment
configuration exists; B9 still owns the complete environment-only overlay and recursive package resources.
PostgreSQL cluster identity and error-type diagnostics are durable across replicas/restarts; conflicting configured IDs
are rejected. SQLite keeps its configured identity and process-local error lifetime. Shared health never publishes raw
exception messages. Missing-module/API red tests for routing, cluster state, leadership, controller and entrypoints remain.

Scheduler leadership uses one detached PostgreSQL session and a key distinct from root lab writes. Heartbeats do not
reacquire recursive locks and leave no idle transaction. Graceful release explicitly unlocks and literally closes its
session; an owned child-process death allows takeover. Every business transaction binds to the exact owning session,
so connection loss cannot reconnect on a fresh business session and commit stale work. Completed jobs retain independent
commit boundaries. The initial whole-tick transaction failed the independent-job regression and is retained as red:
a caught job error erased completed/unrelated work. Session binding fixes B-008 while keeping B3 nested rollback semantics.
Tests check PID identity, process/graceful takeover, lost-session rollback and loss between independent committed jobs.

Full SQLite: 541 passed, zero skips, one existing Starlette warning. Fresh full PostgreSQL17.11: 559 passed, zero skips,
same warning; target audit 363 PostgreSQL and 48 explicitly local SQLite product Stores. The extra 18 cases are ten B3
second-dialect cases and eight real PostgreSQL-specific service/session/controller cases. The test-owned container was
removed. Core mutation control18 passed and all16 mutants killed: owner partitions/router filtering, role thread limits,
physical-session lifecycle/nonrecursive lock/distinct key, session fencing/independent commits, durable diagnostics,
identity conflict and false standby ownership. The final control also strengthens the background-loop spy to watch the
controller entrypoint in either dialect; implementation was unchanged after full suites. Numerical runtime is unchanged
since Part A. Ruff lint/format and documentation formatting pass. Logs include redaction hashes; credentials are excluded.

Primary semantics checked: PostgreSQL17 explicit-locking advisory-lock docs and SQLAlchemy2.0 Connection.detach docs.
Source hashes, patch/new files and exported actual routes identify this milestone.

## What this does NOT show

B4 is still incomplete: PostgreSQL pg_dump-to-backup-storage and an isolated restore drill remain. Basic metrics here
prove ownership/liveness, not B7's full instrumentation. This is isolated CPU/DB testing, not a deployed multi-container
cluster, MinIO/OIDC, full packaged apps, GPU/Windows acceptance or learning. B5–B10 and all MiniCloud C remain. The live
lab and revoked device were untouched; the entire goal remains active. The separate owned development PostgreSQL
container remains available for continuing B4 work; private resource records are excluded.
