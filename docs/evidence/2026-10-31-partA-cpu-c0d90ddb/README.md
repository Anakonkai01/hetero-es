# Part A complete CPU acceptance at src-c0d90ddb

Commit 570b4b90; clean accepted source src-c0d90ddbe800ef358e86d8b7fd09e9f11c0abdb25395e6cc79bf8b11a5eb72d5.
The receipt and raw top-level log SHA-256 values were checked before archiving. This is the completed CPU run after
fixing pinned-model preparation and explicit architecture applicability in the GPU harness.

- acceptance-selftest: 51 passed.
- check-all: ALL PASS (594 seconds).
- Runtime CPU: 3,321 passed / 1,045 skipped (GPU/optional model cases are deliberately unavailable to this CPU profile).
- Backend SQLite: 464 passed, one dependency deprecation warning.
- Python lint/format, Prettier, source-package imports, web/desktop unit/type/lint/i18n/build checks, all fixture web
  browser checks and Worker Electron checks passed. Each raw step log is under checks/.

Command:

```bash
ACCEPT_PYTHON=/home/pc5070ti/projects/heteroes/.venv-backend/bin/python python3 scripts/accept.py run cpu --keep
```

## What this does NOT show

This CPU profile does not establish GPU/performance, 3060 WSL/native, PostgreSQL, cloud services or MiniCloud acceptance.
Its UI checks use isolated fixture labs, not the deployed public lab. GPU and remote acceptance on this source are still
in progress. Original generated screenshots remain in the ignored scratch run; these logs record the completed checks.
