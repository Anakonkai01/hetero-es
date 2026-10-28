# r11 candidate5 build (not published) — 2026-10-20, plan step 3

`BUILD=lf1-20261020-r11-candidate5 scripts/build-apps.sh` at `2c524dd` (code of step 2 is `4ab54c6`; the full check
`ALL PASS` for that code is in `2026-10-20-candidate5-checks`). Output on the Archive disk (UUID `10443D1F443D094C`,
checked before building and before preparing):
`/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261020-r11-candidate5/`. Candidate4 is superseded: it does not contain
the agent/backend/web change that shows why a run is stuck STARTING.

Resources committed in `a162cde`: only the two runtime archives, `runtimeSha256` in both `profile.json` and the build
name in `defaults.json` changed (same shape as candidate4's `d435c3b`). `build.log`: exit 0.

- `runtime-source-worker.txt`: all 103 files of the Worker runtime archive (102 `src/heteroes/*` + `scripts/run_worker.py`)
  are byte-identical to `runtime/`; the file list equals candidate4's. `runtime-source-server.txt`: the 20 `heteroes/*`
  files in the Server archive equal `runtime/src/heteroes/*`. The step 2 change is inside the builds: `agent_command_deferred`
  is in the Worker archive's `product/agent.py`, in the Server archive's `backend/routes_history.py` and in the built web
  asset `eventText-*.js`.
- `installers-prepared.json` (`--prepare-only`, `publiclyPublished: false`, `cloudPublish: false`) and `installers.sha256`
  (the four installer hashes equal the receipt; the two CLI files are hashed too). Nothing is published; the live download
  page and manifest are untouched.
- `build-check.log`: source-copy packaging check (`scripts/build-apps.sh --check`) exit 0, both apps import the shared
  modules.
- `packaged-linux-server.json`, `packaged-server.log`, `installed-server-detail.png`: packaged Lab Server fresh install,
  bootstrap, same-origin HTTP, stop/restart — PASS. `packaged-linux-install.json`, `packaged-worker.log`: packaged Worker
  fresh pinned runtime + GNOME libsecret keyring round trip — PASS. Both ran under
  `dbus-run-session -- xvfb-run -a` with fresh XDG directories, CPU only (`CUDA_VISIBLE_DEVICES=''`), `ELECTRON_RUN_AS_NODE`
  unset. No `heteroes-server` / `heteroes-worker` process was left. Log lines of desktop-bus noise were removed.
- Cleanup: the 5.1 GB packaged-check output and two superseded scratch builds (candidate3, d415f68) were deleted from
  `.scratch/`; system disk free 16 GB → 23 GB.

## What this does NOT show

- No publication or deployment; the builds' default lab is still the live r10 lab, so r11 workers must not be paired
  before the owner's switch.
- No Windows run of candidate5 yet (the Windows installers are built under Wine and unsigned; hashes only). The Windows
  upgrade/restart/uninstall test, device upgrades and GPU self-tests are plan step 4.
- The packaged checks are Linux, CPU-only, driven by a script, not by a person clicking through the UI. The step 2
  behavior (reason shown on a stuck run) is proven by the step 2 evidence, not re-run here against a real failing agent.
