# Windows uninstall of the candidate9 Worker on Thao (2026-10-21 ~19:35 +07)

The plan (`plan-r11-release.md` step 4) asks once before flag day for the Windows upgrade/restart/uninstall test as in candidate4.
Upgrade: candidate8 → candidate9 in `../2026-10-21-candidate9-device-upgrades/` (`windows-installed-verification.log`: build
`lf1-20261021-r11-candidate9`). Restart: the whole-app hard stop of `../2026-10-21-restart-run-candidate9/` (event 4, recovered).
Uninstall: this receipt.

## What happened

1. **The owner uninstalled the app by hand** on the Windows machine after the candidate9 run (not the silent `/S` uninstaller that
   candidate4 used; the exact Windows dialog was not recorded). The installed build before it was candidate9.
2. Afterwards `%APPDATA%\@heteroes` was **still there with about 5.6 GB** (owner's report), and the owner deleted it by hand.
3. Read-only check after both (`after-uninstall.ps1` → `after-uninstall.log`, `appdata-check.ps1` → `appdata-check.log`): no app
   executable or program folder, no `%APPDATA%\@heteroes` at all, no `D:\HeteroES-Worker-data`, no `HeteroES Worker` process, no
   HeteroES entry in the Windows uninstall list, nothing HeteroES in the Recycle Bin. C: 24.1 GB free, D: 796.9 GB free.

## Why `@heteroes` stayed: an AI-made backup next to the app's folder, not the uninstaller

`%LOCALAPPDATA%\Temp\heteroes-system-finish\restore-state.json` (written by an earlier AI session, see
`../../handoff-system-finish-codex.md` lines 80-94) records that the **original r10 Worker's user data was moved to
`%APPDATA%\@heteroes\worker-system-finish-backup`** to be restored later. The uninstaller (`desktop/worker/build/installer.nsh`)
removes `@heteroes\worker` recursively and then the parent `@heteroes` only if it is empty (`RMDir` without `/r`, tested in
`desktop/worker/tests/installer-config.test.cjs`). With the backup folder beside it the parent was not empty and stayed, as designed:
the uninstaller must not delete folders it did not create. So the ~5.6 GB was, by every record, that backup (the old runtime and
model of the r10 Worker). The folder's content was not listed before it was deleted, so this is inferred from the records.

Consequence: the original r10 Worker can no longer be restored (`restore.ps1` would miss its data). It held the revoked live identity
that must never be enabled again, and flag day installs a fresh Worker for the live lab, so nothing planned needs it.

Still on the machine: `%LOCALAPPDATA%\Temp\heteroes-system-finish` (~0.85 GB: the original program 0.35 GB, the c5-c9 installers,
driver logs, registry exports, `researcher.json` = the copied researcher login the handoff says to remove at cleanup). **Deleted
at the owner's request** (`delete-temp.ps1` → `delete-temp.log`: 142 files, 0.833 GB, folder gone, C: 24.9 GB free). Four
`D:\HeteroES-*` staging folders from earlier sessions stay.

## Cleanup of earlier sessions' leftovers (owner's "đồng ý", ~19:45 +07)

Inventory: `inventory.ps1` (Windows) plus a `du` listing on WSL. Deleted on Windows (`delete-windows-leftovers.ps1` →
`delete-windows-leftovers.log`): `D:\HeteroES-r11-long-data-20261020` 120.6 GB, `D:\HeteroES-v3-20261019` 4.6 GB,
`D:\HeteroES-session4-20261020` 2.8 GB, `D:\HeteroES-r11-cpu-guard-probe-20261021` 0.9 GB, `%LOCALAPPDATA%\@heteroesworker-updater`
(old r10 updater installer) and `%LOCALAPPDATA%\HeteroES-v3-20261019`. After: C: 25.1 GB, D: 845.8 GB free; nothing HeteroES left
on Windows.

WSL: `delete-wsl-leftovers.sh` deletes the old research environment (`~/heteroes-venv`, `~/projects/heteroes`, `~/.cache/huggingface`,
m2 config, the c7/c8 run folders in `/tmp`). The AI's SSH call was blocked by the Claude Code permission classifier, so the owner ran
it from the chat (`delete-wsl-leftovers.log`): 10 paths deleted (~5.9 GB), no failure; WSL disk use 23 GB → 17 GB. Kept on purpose until the flag-day smoke run is done: `~/.local/share/heteroes-c4-cpu` (the CPU
coordinator, which uses its own model copy, not `~/.cache/huggingface`), `~/.local/share/heteroes-power` and
`/tmp/heteroes-r11-c9*`. The WSL disk image (`ext4.vhdx`, 33.9 GB on C:) does not shrink by itself; compact it after the last cleanup.

## What this does NOT show

The app's own removal of `@heteroes\worker` cannot be told apart from the owner's manual deletion, because the owner deleted the
parent folder before the check. `D:\HeteroES-Worker-data` being gone points to the uninstaller's `customUnInstall` (only it reads
`data-folder.txt`), unless that was also deleted by hand. The silent uninstaller path of candidate9 was not run; candidate4's
silent run (`../2026-10-20-r11-candidate4/windows-uninstall.log`) is the clean-machine proof. The Windows device record stays in the
isolated lab (offline; its credential was on the machine and is gone).
