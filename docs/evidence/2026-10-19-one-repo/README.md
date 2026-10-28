# 2026-10-19 — one repository, lab moved to a deployed clone of `main`

## What was done
1. **Baseline on the old checkouts** (`hetero-es-m3-runtime` 94668af, `Hetero-ES-LLM-m3` c560d6f), before any change:
   - runtime `pytest`: 2,115 passed, 100 skipped (`baseline/runtime-pytest.log`).
   - `scripts/check-all.sh`: 15 of 17 steps passed. `worker-onboarding` and `worker-station` failed with "Process failed to
     launch" because the shell (started from VS Code) exported `ELECTRON_RUN_AS_NODE=1`, which turns Electron into
     plain Node. Rerun with the variable cleared, both passed (`baseline/*-rerun.log`). `check-all.sh` now clears it itself.
2. **Encrypted archive** of both repositories (`git bundle --all`, every branch) and the live management database:
   `/mnt/Archive-2tb/heteroes-local/archives/2026-10-19-before-one-repo.tar.gz.gpg` (restore-verified, 8 files,
   sha256 e3abb3a5…). Plain copy in `~/.local/share/heteroes-session-archives/2026-10-19-before-one-repo/`.
3. **Merge with full history**: the runtime moved into `runtime/` in one pure-rename commit (2,922 files, all R100),
   then merged into the product history with `--allow-unrelated-histories`. Old branches are kept as
   `archive/runtime/*` and `archive/product/*`. `history-check.txt`: 353 old commits, 0 missing.
4. **First check of the merged repository** found two problems that the old working trees had hidden
   (`merged-main/first-*.log`):
   - `desktop/worker/build/installer.nsh` (the r10 uninstall macro) was never committed: the global `build/` ignore rule
     matched it. Now tracked.
   - `check-web-experiments.mjs` read the template picker before it had loaded (failed once under load, 3 of 3 passes
     alone). It now waits for the option.
   After the fixes: runtime 2,115 passed / 100 skipped, backend 288 passed, `check-all.sh` ALL PASS
   (`merged-main/check-all.log`, `merged-main/runtime-and-backend-pytest.log`).
5. **Lab cut-over** (the owner ran the systemd commands; the lab was idle, queue open, 0 reservations): the user unit now
   runs `~/.local/share/heteroes-lab/app` (a clone of `main` at 79876cb) with its own venv
   `~/.local/share/heteroes-lab/venv-backend` (same packages as the old one: `backend/requirements-cloud.lock.txt`).
   The web build and download links were copied unchanged from the old tree. Read-only public check afterwards:
   `public-verify-after-cutover.json` (`allOk: true`, build r10, Live view stream, notifications). Database
   `quick_check` ok, queue reopened, `5070ti` and `3060-thao` still APPROVED.

## What this does NOT show
- No GPU work ran, and no device was online during the cut-over (`3060-thao` was last seen about 5 days earlier), so a
  real agent poll against the moved lab is not shown.
- Screenshots of the browser checks were not kept (only logs); the pages are the same as in r10.
- The installers were not rebuilt; r10 stays the published build.
