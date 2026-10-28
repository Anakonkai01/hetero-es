# r11 candidate1 Worker and Lab Server builds (not published) — 2026-10-19

Handoff `docs/handoff-v3-audit-recovery.md` section 5 step 6.

## What was built

1. `profile-build.log`: `build-worker-profile.py --profile desktop-v3` at `7acaaca` (same pins as
   `../2026-10-19-r11-profile-v3`; only the runtime archive differs). The output was copied unchanged into
   `desktop/worker/resources/` in `6614e02` (profile, both lock files, v3 `reference.json`,
   `reference-v3-adapter.bin`, `runtime.tar.gz`). `*.bin` was git-ignored, so `.gitignore` now un-ignores
   exactly this adapter and the copy in the qualification evidence (`6785ac5`; that evidence had listed the
   file in SHA256SUMS without committing it).
2. `build.log`: `BUILD=lf1-20261019-r11-candidate1 DOWNLOADS=<repo>/.scratch/r11-builds
   ARCHIVE_UUID=<system disk> scripts/build-apps.sh` — Web UI, refreshed runtimes, Linux unpacked and
   Windows NSIS (Wine, **unsigned**) for both apps, into
   `.scratch/r11-builds/lf1-20261019-r11-candidate1/` on the system disk. The build-generated resource
   refreshes are committed in `cb157f3`, so the installers correspond to that tree.
   `installers.sha256` / `installer-sizes.txt`: Worker setup `a85af2e7…` (≈99 MB), Lab Server setup
   `ea8170f7…` (≈100 MB). The packaged Worker (Linux and Windows) contains `resources/worker/
   reference-v3-adapter.bin` identical to the repository file.
   Nothing was copied to the published downloads, no manifest changed, no installer was published.

## Packaged checks on this machine

- `packaged-linux-install.json`: the real packaged Linux Worker, isolated XDG profile, real GNOME
  libsecret keyring under Xvfb, installed a **fresh** runtime from the pinned profile (shared verified
  download cache on the checked Archive disk) in 59 s; READY.json says `"profile":"desktop-v3"`.
- `packaged-linux-qualify.json` (owner-authorized GPU, `--gpu`, `HETEROES_GPU_ACCEPTANCE=1`): the app's own
  self-test on the RTX 5070 Ti went through `qualification.main` → v3 and returned `runtimeProfile:
  desktop-v3`, `recipeVersions: [3]`, and `recipeV3`/`recipeV3Lora` evidence **identical** to the native
  Windows RTX 3060 result in `../2026-10-19-v3-qualification-reference`.
- `packaged-server-*.log`: `scripts/check-linux-server.cjs` first used a wrong executable name (launch
  ENOENT, nothing installed). The second run installed the Lab Server, initialized and started a lab and
  read its telemetry, then **failed** at a UI step looking for a button named "Chi tiết". No Worker, Lab
  Server or Web source contains that label any more, and neither `desktop/server/src` nor this script changed
  on this branch (since `30bc689`), so the selector is stale from earlier UI work. It was not changed here; the remaining API/stop/restart steps of that script did not run. No server process remained.

## What this does NOT show

- No Windows installer was run. Native Windows C: has about 3.5 GB free and the r10 runtime there uses
  4.1 GB; an r11 runtime (≈3 GB download, more once extracted) does not fit without the owner freeing space
  or choosing another disk. No user data was deleted.
- Installers are unsigned test builds; no install/run/restart/stop/uninstall acceptance with the owner
  (handoff step 7), no enrollment, approval, live job, deployment or flag day.
- The Lab Server packaged check is incomplete (stale UI selector above).
- The candidate's default lab URL is the live lab, which still runs r10 (`79876cb`); pairing an r11 Worker
  there before the owner's server switch is not supported.
