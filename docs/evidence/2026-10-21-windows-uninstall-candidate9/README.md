# Windows uninstall of the candidate9 Worker on Thao (2026-10-21 ~19:35 +07)

The plan (`plan-r11-release.md` step 4) asks once before flag day for the Windows upgrade/restart/uninstall test as in candidate4.
Upgrade: candidate8 → candidate9 in `../2026-10-21-candidate9-device-upgrades/` (`windows-installed-verification.log`: build
`lf1-20261021-r11-candidate9`). Restart: the whole-app hard stop of `../2026-10-21-restart-run-candidate9/` (event 4, recovered).
Uninstall: this receipt.

- **The owner uninstalled the app by hand** on the Windows machine after the candidate9 run (not the silent `/S` uninstaller that
  candidate4 used; the exact Windows dialog was not recorded). The installed build before it was candidate9.
- Read-only check afterwards over SSH (`after-uninstall.ps1`, output `after-uninstall.log`): the app executable and its program
  folder are gone, the app data `%APPDATA%\@heteroes\worker` is gone, the data folder `D:\HeteroES-Worker-data` the app created is
  gone, no `HeteroES Worker` process, no HeteroES entry left in the Windows uninstall list. C: 24.1 GB free, D: 796.9 GB free.
- The four `D:\HeteroES-*` folders still present are staging/test folders made by earlier sessions, not by the app (the newest is
  from 02:48 today); the uninstaller is not meant to remove them, as in candidate4. Left as they are.

The result equals candidate4's (`../2026-10-20-r11-candidate4/windows-uninstall.log`: app, app data and data folder removed,
unrelated staging folders kept).

## What this does NOT show

No "before" snapshot was taken right before the uninstall (the last one is the candidate9 install receipt). The silent uninstaller
path of candidate9 was not run. The Windows device record stays in the isolated lab (offline; its credential was on the machine and is
gone with the app data). For flag day the Windows Worker is a fresh install pointing at the live lab.
