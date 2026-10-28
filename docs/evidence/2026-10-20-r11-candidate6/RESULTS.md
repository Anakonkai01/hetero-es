# Candidate6 prepared, source-checked and packaged Linux checks pass

Build `lf1-20261020-r11-candidate6` exited 0. Runtime source is implementation f5d311b; resources are
committed in **0281e04**. Output is the fresh Archive directory named for the build; the build and
preparation tools enforce UUID 10443D1F443D094C. Pinned Python/wheel/model/reference identities are unchanged.

- Worker archive: **104 source files**, all byte-identical to runtime; the new `eval/cpu_guard.py` SHA256
  equals the two-GPU proof. Server: **63 Python source files** (backend plus shared runtime), all equal.
  Both Linux and Windows unpacked resource archives/profiles exactly equal the committed resources.
- Runtime hashes: Worker `aa74bad820b9677fdaa1f0b81261264479c468c52b90636ae956232049596c38`, Server
  `1a74f639096d7319b27d511e535ecf8661e1c5e3098538ea9602adfeaed34eca`.
- `installers-prepared.json`: **prepare-only**; installer/CLI hashes are retained in `installers.sha256`.
  Source-copy packaging passes for both apps and shared-module imports (`source-copy-packaging.json`).
- Packaged Linux Worker fresh pinned installation and real GNOME libsecret round trip: PASS.
  Packaged Linux Server fresh CPU install/bootstrap, same-origin HTTP and stop/restart: PASS.
  Explicit isolated XDG directories, Xvfb/D-Bus, CUDA hidden, ordinary Electron mode. Original raw D-Bus
  diagnostic noise is preserved in logs; both check processes exit 0.
- After preserving receipts, removed only the three newly created disposable packaging-check trees,
  freeing roughly 6 GB on the system disk. The isolated devices' original state was not removed.
- Private tailnet-only candidate transport serves this build on port **8802** for subsequent isolated
  device upgrades. It is separate from public installer links/manifest; the earlier 8801 service remains.

## What this does NOT show

No public installer publication, live deployment, Windows execution or four-device installed acceptance
yet. The Windows installers were built under Wine; native Windows GPU/upgrade/uninstall checks remain.
Linux checks are scripted, CPU-only fixtures and do not constitute an ordinary desktop walkthrough.
No 50-generation managed acceptance or outage/retry/full independent parity claim. Existing candidate5
artifacts and its paused failed run remain untouched; flag-day confirmations remain required.
