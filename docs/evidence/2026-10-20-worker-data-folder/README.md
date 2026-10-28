# Worker data folder on another drive — 2026-10-20

Owner decision (2026-10-19): instead of asking for space on C:, the Worker may keep its runtime elsewhere. The native
Windows 3060 has ~3.5 GB free on C:, too little for an r11 runtime.

## What this does

- Install screen: "Use another drive or folder" (before a runtime is installed) opens a folder picker; the app creates
  `HeteroES-Worker-data` inside the chosen folder and keeps runtimes, model, downloads and artifacts there
  (`storage.json` gains `runtimes`; the existing disk-space check applies to that drive). The current data folder is
  shown. Refused while setup runs, after a runtime is installed (`RUNTIME_ALREADY_INSTALLED`), and for a relative,
  missing or non-directory path.
- Uninstall (`build/installer.nsh`): reads `data-folder.txt` (written by the app next to `storage.json`) and removes
  that folder only if its name ends in `\HeteroES-Worker-data`; the user's chosen folder and its other files are never
  removed. electron-builder runs `customUnInstall` before it deletes the app data folder holding the marker
  (`node_modules/app-builder-lib/templates/nsis/uninstaller.nsh`: macro at line 156, app data removal from line 223).
  An upgrade keeps everything, as before.
- Tests: `desktop/worker/tests/setup.test.cjs`, `installer-config.test.cjs`; Worker unit 81 + 5 passed, tsc, i18n,
  Prettier clean. Mutation 8/8 killed (first run: relative-path survivor, closed by a test).

## What this does NOT show

- Not run on Windows: no real NSIS uninstall, no dialog on a real D: drive, no install there. That needs candidate2
  installers and a Windows run.
- Only a fresh install can choose; moving an installed runtime is not supported.
