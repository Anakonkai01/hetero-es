# r11 candidate4 builds (not published) — 2026-10-20, session 5

`BUILD=lf1-20261020-r11-candidate4 scripts/build-apps.sh` at `e123935` (full check ALL PASS at 595faa1 in
`2026-10-20-session5-checks/checks-595faa1`; e123935 only adds that receipt). Candidate3 was superseded because the first
real managed run on it found two bugs (managed Python rewards refused by the coordinator agent; cancelled-before-accept
runs never released). Output on the Archive disk: `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261020-r11-candidate4/`.
Resources committed in `d435c3b`: only runtime archives, `runtimeSha256` and the
build name changed. `runtime-source-*.txt`: every heteroes file in both runtime archives equals the repository.

- `installers-prepared.json` (`--prepare-only`, `publiclyPublished: false`) and `installers.sha256`. Nothing published.
- `build-check.log`: source-copy packaging check PASS. `packaged-linux-server.json`: packaged Lab Server PASS.
  `packaged-linux-install.json`: packaged Worker fresh pinned runtime + GNOME libsecret PASS (run under dbus-run-session).
- Linux CLI: the one-line installer installed candidate4 on Thao's WSL (66 s on Quang for candidate3) and passed the CPU
  coordinator self-test; see `2026-10-20-managed-cpu-coordinator`.
- Isolated lab upgraded to candidate4; local 5070 Ti desktop Worker upgraded, runtime installed, GPU self-test passed.
- **Native Windows (Thao RTX 3060)**: `windows-upgrade.log` — silent in-place upgrade to candidate4 with installer hash
  check, isolated pairing and D: model cache kept; runtime install, GPU self-test (desktop-v3, Windows, qualified for the
  pinned model) and sign-in passed; it was the GPU worker of the managed run with exact parity. Quit → relaunch: the app
  came back as candidate4, reconnected, contribution stayed OFF for the new boot. `windows-uninstall.log` — silent
  uninstall removed the app, its app data and the `D:\HeteroES-Worker-data` folder it created, and left the unrelated
  `D:\HeteroES-session4-20261020` staging folder untouched.

## What this does NOT show

- No publication/deployment; the default lab inside the builds is still the live r10 lab (owner's r11 switch pending).
- No Windows Lab Server or Windows CPU coordinator acceptance; the Windows checks were driven through the app's own
  bridge (remote-debugging driver), not by a person clicking through the UI.
- The 3060 Windows device record remains in the isolated lab (approved, offline, credential deleted by the uninstall).
