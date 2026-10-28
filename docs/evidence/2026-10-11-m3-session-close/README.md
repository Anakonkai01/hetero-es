# Session-close evidence — 2026-10-11

Owner requested complete local handoff and commits. This closeout performs no
GPU campaign and leaves contribution preferences and dispatch hold unchanged.

`state.json` records the authenticated read-only management observation, empty
local CUDA process query, 21 preserved metadata experiments, private archive
location, product snapshot SHA-256 and verified SQLite integrity. Seven SQLite
snapshots use `Connection.backup`, including live metadata, stopped campaign
ledgers and agent outbox; WAL/SHM files are excluded. Three installer copies retain
their build-time SHA-256 values. No credentials are included in this evidence.

The archive's private manifest contains per-file SHA-256, source paths, copy or
hardlink method, database integrity and table counts. Final local source revisions
and bundle verification live in `git-bundles.json` inside the archive. Large
stopped-campaign files share inodes with their archive copies; this same-disk
archive cannot provide disk-failure protection. Cloud remains deferred.

See [the session handoff](../../m3-session-handoff.md) for source branches, services,
restart commands, budget, limitations and the next packaged Linux GPU test.
