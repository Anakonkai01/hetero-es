# Part A CPU acceptance at src-ede4338e

Committed source: 21d7f591 (source fix a5d81cbd), source identity
`src-ede4338ef54a443a0ecc33a2bc96ea836ea188b856727ed63e095594a7b8b3a4`.
Both selected checks passed on 2026-11-01. The controller receipt reports clean source. Copied top-level logs were
verified against the receipt SHA-256 before archival; every child check log is retained here as well.

Acceptance selftests: 58 passed. check-all: ALL PASS, including runtime 3,324 passed / 1,045 skipped with CUDA hidden,
backend SQLite 464 passed, Python lint/format, Prettier, source-package imports, frontend/desktop units, TypeScript,
ESLint, i18n, web/worker builds, all browser fixture contracts and both Electron fixture contracts.

## What this does NOT show

CPU deliberately hides CUDA. Its skips are not GPU acceptance. This receipt does not prove the new source on GPU,
native Windows, PostgreSQL, OIDC, MinIO, MiniCloud, a deployed lab or a learning task. Those remain separate checks.
