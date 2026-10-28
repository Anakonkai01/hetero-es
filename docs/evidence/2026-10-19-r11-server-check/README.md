# r11 candidate1 packaged Lab Server check rerun — 2026-10-19

Handoff `docs/handoff-r11-candidate.md` open item 2.

## What this does

`scripts/check-linux-server.cjs` looked for a button named "Chi tiết". That label is the Vietnamese
translation of the telemetry switch's "Detail" view (`packages/product-ui/src/telemetry.tsx`); the UI language
follows the detected system language, so on this English-locale machine the button reads "Detail". The script
now clicks the second button of `.telemetry-switch` and asserts `aria-pressed="true"`, independent of language.

Rerun on the unchanged candidate1 build
(`.scratch/r11-builds/lf1-20261019-r11-candidate1/server/linux-unpacked/heteroes-server`), fresh isolated
XDG directories under `.scratch/r11-packaged-server-3/`, `dbus-run-session -- xvfb-run -a`,
`ELECTRON_RUN_AS_NODE` unset. Archive disk UUID `10443D1F443D094C` checked before the run (the script creates
one `server-proof-*` storage folder there, as designed).

Result: `PASS packaged Linux CPU Server install/bootstrap/same-origin/lifecycle.` — `packaged-linux-server.json`
(all steps of the script, including the API, stop and restart steps that did not run before) and
`packaged-server.log` (desktop-bus noise lines removed). No `heteroes-server` process remained (`pgrep -x`).

## What this does NOT show

- Not a Windows Lab Server run, not signed installers, not an owner walkthrough.
- The build is candidate1; later r11 changes (new coefficient rules, Countdown scorer, runtime-on-another-drive)
  need a new candidate and a new run of this check.
- No deployment or flag day; the live lab still runs r10.
