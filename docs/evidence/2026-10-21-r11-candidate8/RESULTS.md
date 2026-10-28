# Candidate8 prepared, source-checked and packaged Linux checks pass

Build `lf1-20261021-r11-candidate8` (desktop resources `ea5c5b9`). Output is the Archive directory named for the build.

- **CPU gate** before the build: `../2026-10-21-r11-candidate8-checks/` 23/23 ALL PASS (backend 393, runtime 2583 passed, 102 skipped).
- **Prepare:** `installers-prepared.json`, prepare-only (`candidate8-prepare.log`: `publiclyPublished: false`).
- **Source bytes** (`compare_runtime_source.py` → `runtime-source-comparison.json`):
  - Worker archive: **105 files**, all byte-identical to `runtime/`; `membership.py` present; runtime SHA256
    `b377c9c94cea16817978c67d32e72d0dea479c13df42682467842f374c46a62b`.
  - Server archive: **182 files** (63 Python), all byte-identical to `backend/`, `runtime/src/` and the build's `web/`;
    runtime SHA256 `f4348322280ef31be6f27240f47247b5f5aa25ad48e6103f905f7e5256ab23c1`.
  - Linux and Windows unpacked resources equal the committed `desktop/*/resources`; the Worker bundle contains
    `worker_restarted` (the fix).
- **Source-copy packaging:** `source-copy-packaging.json` PASS.
- **Packaged Linux Server:** `packaged-linux-server.json` PASS (first try).
- **Packaged Linux Worker:** fresh pinned install and a real GNOME libsecret round trip, `packaged-linux-install.json` PASS
  on the second try (540 s).

## Deviations

- **First packaged Worker check failed:** `TimeoutError: Timeout 30000ms exceeded` before a window appeared
  (`candidate8-packaged-worker-attempt1-launch-timeout.log`), the same symptom as candidate7's first Server check: a cold
  first launch of an app from the Archive (fuse/NTFS) volume. The rerun with a fresh XDG tree and output passed. The
  cause is still not proven; it was not retried silently and no code changed between the two runs.

## What this does NOT show

No device, Windows or installed-device receipt, and not the 50-generation acceptance. Windows installers are built under
Wine. Linux checks are scripted CPU-only fixtures. Nothing was published, deployed, merged or pushed.
