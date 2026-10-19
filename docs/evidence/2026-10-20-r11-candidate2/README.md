# r11 candidate2 builds (not published) — 2026-10-20

`BUILD=lf1-20261020-r11-candidate2 DOWNLOADS=<repo>/.scratch/r11-builds ARCHIVE_UUID=<system disk> scripts/build-apps.sh`
at `35e00fd`: everything of candidate1 plus the coefficient rules, alpha schedules, momentum records, evaluation chunk,
countdown scorer, managed/web options and the Worker data folder on another drive. Refreshed resources committed in
`3419876` (only `runtimeSha256` and the build name changed). Unsigned installers in
`.scratch/r11-builds/lf1-20261020-r11-candidate2/` (`installers.sha256`).

Packaged Linux checks (fresh isolated XDG directories, Archive disk UUID checked): `packaged-linux-server.json`
(Lab Server install/bootstrap/same-origin/lifecycle: PASS) and `packaged-linux-install.json` (Worker installed a
fresh runtime from the pinned profile: PASS). No server or worker process remained.

Countdown pilot 2 (`.scratch/countdown/pilot2`) was stopped by the owner's choice after 2 of 300 generations to free
the GPU for GSM8K; its ledger is kept, nothing is claimed from it.

## What this does NOT show

- No Windows run of candidate2 (installer, D: data folder, uninstall) and no GPU self-test of the packaged Worker.
- Not published; the candidate's default lab is the live lab (r10), which must not pair r11 workers before the switch.
