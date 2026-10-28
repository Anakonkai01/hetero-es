# Candidate7 prepared, source-checked and packaged Linux checks pass

Build `lf1-20261021-r11-candidate7` (resources `638f8e1`). Output is the Archive directory named for the build
(UUID 10443D1F443D094C checked). Pinned Python, wheel, model and reference identities are unchanged.

- **Prepare:** `installers-prepared.json`, prepare-only (`candidate7-prepare.log`: `publiclyPublished: false`).
- **Source bytes** (`compare_runtime_source.py` → `runtime-source-comparison.json`):
  - Worker archive: **105 files**, all byte-identical to `runtime/`; `src/heteroes/product/membership.py` present.
  - Server archive: **182 files** (63 Python, plus the built web), all byte-identical to `backend/`,
    `runtime/src/` and the build's `web/`. Every shared `heteroes` module the backend imports is shipped.
  - The Linux and Windows unpacked resources of both apps equal the committed `desktop/*/resources` files.
  - Runtime SHA256: Worker `57b0faf6d31a394afef5fd4760f1d0da6ebbe4e922dce5fb9eea392917c3adc7`, Server
    `fbb2cb7c8dbe6181b3f7089ac23fcd86f19ee813bad626d00bafcf376ee3926a`.
- **Source-copy packaging:** both apps build from a fresh source copy and their shared modules import
  (`source-copy-packaging.json`, source commit `63d9b0a`).
- **Packaged Linux Worker:** fresh pinned install and a real GNOME libsecret round trip: PASS (600 s, because
  the isolated XDG tree was on the Archive volume).
- **Packaged Linux Server:** fresh CPU install/bootstrap, same-origin HTTP, stop/restart: PASS on the second run.

## Deviations from the predeclaration

- The README said `product/membership.py` must be in **both** archives. The Server only ships the shared modules
  its backend imports, and the backend does not import `membership.py` (the lab side of membership lives in
  `backend/`). The check was changed to "every backend import is shipped" instead.
- **First Server check failed:** `electron.launch: Timeout 30000ms exceeded` before a window appeared
  (`candidate7-packaged-server-attempt1-launch-timeout.log`). It was the first launch of the app from the Archive
  (fuse/NTFS) volume. The rerun with a fresh XDG tree passed. The cause is not proven; the retained guess is a slow
  cold start from that volume, not a product fault.

## What this does NOT show

No device, Windows or installed-device receipt, and not the 50-generation acceptance. Windows installers are built
under Wine. Linux checks are scripted CPU-only fixtures, not an ordinary desktop walkthrough. Nothing was published,
deployed, merged or pushed.
