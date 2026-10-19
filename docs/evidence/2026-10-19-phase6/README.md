# Phase 6 — one handoff, complete CPU gate and isolated Linux packaging

The current entry points are root `README.md`, root `AGENTS.md` and `docs/HANDOFF.md`. Superseded plans/session guides and
runtime bootstrap instructions are preserved under `docs/archive/`; research MASTER/STATUS, numerical contracts, claims
audit and raw artifacts remain. Existing runtime research follow-ups moved to `docs/RUNTIME-TODO.md`, outside this cleanup.
The quickstart describes published r10. `.git-blame-ignore-revs` records the separate format-only commit `a3cf14e`.

## Final verification

- `check-all.log` and `checks/`: all **22 CPU steps pass**. Runtime **2,110 passed, 100 skipped**; backend **283 passed**;
  frontend units **74**, Worker units **81**, Server units **1**, shared UI units **5**. No tests were removed in this phase.
  The command now includes runtime tests, Ruff lint/format, pinned Prettier and isolated source-package import checks.
  Types, ESLint, i18n, builds and browser/Electron fixture flows pass. Translation audit has zero missing/unused keys.
- `linux-packaging.log` / `linux-packaging.json`: `scripts/build-apps.sh --check .scratch/cleanup-linux` built both Linux
  unpacked apps in a source copy. Each packaged executable imports shared runtime/download and setup modules from ASAR.
  Source baseline is `a3cf14e`, plus the new validation tooling; later changes are documentation and shell comments.
  The source checkout's pinned tarballs/profiles and public downloads were not replaced. Disposable apps stay ignored
  under `.scratch/`. Ordinary builds clear inherited `ELECTRON_RUN_AS_NODE`; only the intentional module probe sets it.
- `ast-final.json`: rechecked all **287 Python ASTs** against `ffb04a0`, with no changes. This includes frozen numerical
  modules. The new packaging checker is additional tooling; the strict format-only proof is in the phase-5-format folder.
- `history-check.json`: all **353 commits** from the original two repositories remain reachable, with 33 archive branches.
  Old linked worktrees share these histories; their archived absolute Git paths were not changed or used for development.
- `public-lab-final.json` / `.log`: public health/pages, administrator login, a completed timeline/stream and notification
  reads pass. All four published Windows/Linux Worker/Server downloads match their manifest size and SHA-256; build is
  still **lf1-20261014-r10**. `public-lab.log` retains the initial transient TLS timeout; the fresh rerun passed completely.
- `public-pages/`: 19 live pages opened in Vietnamese/light/desktop; no overflow, console/page errors or missing translation.
  This is the deployed r10 UI, separate from the fixture UI checks of the cleanup source.
- `deployed-lab-readonly.json`: all three services alive, SQLite quick check `ok`, deployed commit unchanged at `79876cb`.
  `5070ti` remains APPROVED; `3060-thao` remains REVOKED, with its historical 2026-10-14 revocation audit. No device choice,
  dispatch setting, experiment or private configuration was changed. Login checks create only temporary auth sessions.
- `verification.json`: machine-readable acceptance summary, maintained-document relative-link audit and unchanged tracked
  installer-resource check. Historical evidence files are untouched; only the approved missing 2026-10-13 index was added.

Local `main` is fast-forwarded from `refactor/cleanup` only after this gate. That does not deploy the separate live clone.
There is no push, tag, release or installer publication.

## What this does NOT show

No new GPU computation, learning claim, multi-GPU run, native Windows execution or clean end-user installation of these
cleanup builds. Linux checks prove unpacked packaging and module resolution; they do not repeat full fresh-runtime
installation acceptance. Browser/Electron product flows use disposable fixtures and recorded runs. Public checks verify
the existing deployment and installer bytes, not deployment of cleanup code. Installer polish/r11, demo rehearsal and the
identity/epoch/export follow-ups remain separate work. Existing policy findings are recorded in `docs/SECURITY-NOTES.md`.
