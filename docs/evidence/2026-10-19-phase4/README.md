# Phase 4 — one shared source and reusable policies

Baseline: `8226f32`. The backend imports CPU-safe telemetry and study contracts directly from `runtime/src` in a
checkout. The Server source packager includes only the ten files listed by `backend/runtime_sources.py`; isolated
source-package imports confirm neither Server nor Worker imports torch. The old copied directories, provenance files
and refresh-monitoring generator are removed.

`desktop/shared` is a production npm workspace shared by both Electron apps. It owns download verification, bounded
process execution, safe extraction and diagnostics. The Server no longer relies on generated copies of Worker files.
Dependency pins are preserved; no published runtime tarball/profile or installer is replaced.

`policies.py` centralizes backup validation, settings, active/admin permission checks, Recipe v2 qualification,
storage status, device reservations and strict process-drain checks. The two old Strict bases intentionally differed:
the shared `Strict` forbids extra fields; `FiniteStrict` additionally forbids nonfinite numbers. Their behavior is kept.
`config.py` rereads private configuration so public address changes are still observed. Product identities/status sets
are shared constants. Agent command enqueueing now has a public method.

Backend: 277 → 282 passed. Five obsolete provenance/generator cases were replaced by two shared-source/package
contracts and eight policy cases. The first run caught a helper/route name collision; the helper alias was corrected
before the final green run. `red.log` and `drain-red.log` show the new contracts failing before their implementation.
`focused.log`, `source-packages.log`, `desktop.log`, `mutation.log`, `check-all.log` and `checks/` contain the receipts.
Four scratch mutants exercise boolean backup input, dispatch hold, unknown coordinator ownership and omitted CPU source.
All four are killed after a passing control.

## What this does NOT show

No GPU work, native Windows test, live deployment or installer publication. Source tarball checks are distinct from
Electron packaging; final Linux unpacked validation belongs to the completion check. Browser/Electron checks use fixtures.
The numerical runtime sources are unchanged; scientific raw artifacts and prior evidence remain untouched.
