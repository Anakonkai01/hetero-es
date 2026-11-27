# 2026-11-27 — the packaged Windows Worker app on the lab (RTX 3060, native Windows 11)

Machine `3060-quang` (RTX 3060 12 GB, Windows 11 26200, driver 617.42; its LAN address is `<lan-ip>` here). The app was
driven the way its page drives it: `window.worker.call(action)` over the DevTools protocol, by a script run with the app's
own executable (`ELECTRON_RUN_AS_NODE=1`), so nothing else was installed on the machine (`scripts/drive-app.cjs`,
`scripts/drive-steps.cjs`). The Electron window was open on the machine's desktop throughout.

## Steps and results

1. **Download and install** (`scripts/install-app.ps1`): `HeteroES Worker-0.1.0-20261127-fdf359a3-Windows.exe` downloaded
   from `https://lab.heteroes.site/downloads/` (SHA-256 `af1b6588…`, equal to the published manifest), installed with
   `/S` into `%LOCALAPPDATA%\Programs\@heteroesworker` (361 MB).
2. **Data folder.** C: had 9.6 GB free. A first start used the default data folder `%APPDATA%\@heteroes\worker` (the
   preseeded `storage.json` had been written to `%APPDATA%\HeteroES Worker`, which the app does not use) and began writing
   the runtime to C:; it was stopped after ~190 MB and that folder deleted. The app's own check would have allowed the
   7.7 GB install and left about 2 GB on C:; commit `472ef70f` makes both apps keep 5 GiB free. The second start used
   `storage.json` in the real folder, with the same content as the page's "choose a drive" action
   (`D:\HeteroES-Worker-data`); `drive-app.cjs` refuses to install when the data folder is not on D:.
3. **Install + self-test** (`app-logs/drive.jsonl`): runtime READY in 3 min 30 s (torch 1.9 GB in ~45 s), self-test
   passed on the RTX 3060 (update 0.459 s per seed).
4. **Pair and approve** (`app-logs/pair.jsonl`): `connect` → `login` (owner account; the credentials file was deleted by the
   driver on read and never logged; the session lives only in the app's memory) → `pair` as `3060-quang-windows`
   (device `c092739c…`, PENDING) → approved by the lab owner through the admin API → contribution ON (`app-logs/on.jsonl`).
5. **Strict qualification on the lab**: job `67a2ddbc…` for Qwen2.5-0.5B with `strict_b22_v1` COMPLETED (before
   `fdf359a3` this step failed with `No module named 'cuda'`).
6. **Run `e6534a18`** (`runs/e6534a18-windows-only.json`, script `scripts/windows-app-run.py`): coordinator 5070 Ti, the
   Windows app as the only worker; Qwen2.5-0.5B, Countdown, population 8, 3 generations, 128 tokens, `strict_b22_v1`:
   COMPLETED, 24/24 candidates by the app, 3.43 s per candidate. No audits (one worker).
7. **Run `f76cdb6a`** (`runs/f76cdb6a-two-gpus.json`, `runs/f76cdb6a-audits.json`): same configuration, both the 5070 Ti
   (Linux CLI worker) and the Windows app as workers, audit rate 0.5: COMPLETED, 21 + 3 candidates, **14/14 audits
   matched, all 14 cross-device** (11 candidates of the 5070 Ti re-scored by the Windows app, 3 of the app re-scored by the
   5070 Ti): SM120 on Linux and SM86 on native Windows give the same result hashes.
8. **Upgrade** (`scripts/upgrade.ps1`, `app-logs/after-upgrade.jsonl`): app quit through its own `quit` action, installer
   `20261127-472ef70f` downloaded from the lab (SHA-256 `52c0d3cd…`, published), installed over it with `/S`. After the
   restart: build `20261127-472ef70f`, same device `c092739c…` APPROVED and ONLINE, runtime still installed (no download),
   data folder `D:\HeteroES-Worker-data`, self-test kept, not signed in (the owner session did not survive the restart).

## What this does NOT show

- One Windows machine and one GPU model (SM86); two runs of 3 generations each with the 0.5B model. No long run, no
  1.5B model, no fault (crash, leave, rejoin) of the Windows app and no speed claim beyond these short runs.
- The onboarding page itself was not clicked: actions were called through the page's API. The data-folder choice was
  made by writing the same `storage.json` the page writes, not by the folder dialog.
- The uninstaller was not run.
