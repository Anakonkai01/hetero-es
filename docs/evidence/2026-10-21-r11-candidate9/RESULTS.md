# Candidate9 prepared, source-checked and packaged Linux checks pass

Build `lf1-20261021-r11-candidate9` = candidate8 + fix `f21cc1f` (the two c8 restart causes). Desktop resources `2475135`.
Steps as for candidate8 (`../2026-10-21-r11-candidate8/README.md`), output in the Archive directory named for the build.

- **CPU gate** before the build: `../2026-10-21-r11-candidate9-checks/` 23/23 ALL PASS.
- **Prepare:** `installers-prepared.json`, prepare-only (`candidate9-prepare.log`: `publiclyPublished: false`).
- **Source bytes** (`compare_runtime_source.py` → `runtime-source-comparison.json`): Worker archive 105 files, all equal
  to `runtime/`, runtime SHA256 `9a553d2dfae92859b4a41a12a8bb946bed8743ceb531745ffef689e4e7e9ae41`. Server archive
  182 files (63 Python), all equal, runtime SHA256 `ce3c12810f899aab8e9034357fd5b86c1963413bb6df2dc9d0326cd9eb83104b`. The
  Linux and Windows unpacked resources equal the committed ones. The Worker runtime contains `worker_restart_deferred`.
  Both Worker `app.asar` files contain the new `recordAgentFailure(error, failed)` call of the `service.cjs` fix.
- **Source-copy packaging, packaged Linux Worker, packaged Linux Server:** all PASS on the first try (`package-checks.sh`,
  16:03-16:15).

## What this does NOT show

There is no device, Windows or installed-device receipt and no run. The Windows installers are built under Wine. The
Linux checks are scripted, CPU-only fixtures. Nothing was published, deployed, merged or pushed.
