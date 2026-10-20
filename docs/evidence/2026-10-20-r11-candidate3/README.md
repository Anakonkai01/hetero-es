# r11 candidate3 builds (not published) — 2026-10-20, session 5

`BUILD=lf1-20261020-r11-candidate3 scripts/build-apps.sh` at `fbf8c65` (full check ALL PASS in
`2026-10-20-session5-checks/checks-final`), on the Archive disk (UUID 10443D1F443D094C verified by the script):
`/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261020-r11-candidate3/` with web, Worker, Lab Server and the
headless Linux CLI (`cli/`). Refreshed resources committed in `1d0b6ba` (runtime archives, `runtimeSha256`, build name).
`runtime-source-*.txt`: every heteroes Python file in both runtime archives equals the repository file (Worker 102,
Server 20 including `product/cpu_coordinator.py`). `build.log` is the build output.

- `installers-prepared.json`: `publish-local-installers.py --prepare-only` receipt (`publiclyPublished: false`) with the
  four app installers and the CLI script/bundle; `installers.sha256` lists the same bytes. Nothing was linked or published.
- `build-check.log`: `scripts/build-apps.sh --check` source-copy packaging check, PASS.
- `packaged-linux-server.json` / `packaged-server.log` / `installed-server-detail.png`: packaged Lab Server fresh install,
  bootstrap, same-origin, lifecycle, PASS.
- `packaged-linux-install.json` / `packaged-worker.log`: packaged Worker fresh pinned runtime install with real GNOME
  libsecret, PASS. `packaged-worker-no-dbus.log` is the first attempt, run without `dbus-run-session`: the keyring was
  unreachable (`safeStorage` encryption unavailable) — a harness mistake, not an app defect.

## What this does NOT show

- No publication, deployment or live change. The candidate's default lab is the live r10 lab, which must not pair r11
  workers before the owner's switch.
- No GPU self-test of the packaged Worker, no Windows install of candidate3 and no managed run here (see later evidence).
- The packaged Lab Server ships no downloads directory, so it does not show the Linux CLI command by itself; the live lab
  serves downloads from the publisher's links.
