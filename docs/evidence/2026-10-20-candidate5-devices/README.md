# Plan step 4: isolated lab and devices upgraded to r11 candidate5 — 2026-10-20 evening (Sonnet 5.5)

Build and hashes: `../2026-10-20-r11-candidate5/` (not published). The public lab was not touched; everything below is the
isolated lab (`.scratch/isolated-lab`, http://100.110.165.40:8790, own XDG directories and storage folder).

| Machine | What was done | Result |
|---|---|---|
| Isolated Lab Server (5070 Ti box) | `start-c5.sh` → packaged candidate5 Lab Server on the existing XDG dirs | new runtime directory `3de3eb14322c` installed, `/api/v1/health` ok, `routes_history.py` of that runtime contains `agent_command_deferred` |
| 5070 Ti desktop Worker | `worker5070/start-c5.sh` → candidate5 Worker, runtime install, GPU self-test, researcher sign-in | self-test passed on RTX 5070 Ti 16 GB, `desktop-v3`, recipe 3, qualified model hash `af52722f…533c`; device `5e1b7184` ONLINE, approved, contribution OFF |
| Thao WSL (CPU coordinator) | one-line `install-worker.sh` from a private HTTP server (`--bind` Tailscale address), in place on `~/.local/share/heteroes-c4-cpu` after removing the old runtime and the old run checkpoints (test data; private copies are in `.scratch/session5-managed/thao-run`) | runtime `49e0c502675a` (= Worker `runtimeSha256` prefix), install 33 s, `selftest --device cpu` passed; pairing kept (device `47e0546d`, approved) |
| Thao native Windows (RTX 3060) | silent install of `HeteroES Worker-…-candidate5-Windows.exe` (hash checked against the prepared receipt), data folder `D:\HeteroES-Worker-data`, connect to the isolated lab, sign in, runtime install, GPU self-test, pair, admin approval | self-test passed on RTX 3060 12 GB, `desktop-v3`, Windows, qualified model hash `af52722f…533c`, 0.685 s/seed; new device `8f3d6919` APPROVED, ONLINE, contribution OFF (the old record `106afff2` of the uninstalled candidate4 Worker is still in the lab, offline) |

Free space (Windows C:): Thao 16.5 GB before the installer, 16.1 GB after it (runtime and models go to D:); WSL upgrade did not
change it (17 GB, the old runtime was removed first); Quang 6.9 GB before and after, see below. See `windows-install.log`.

## Quang (3060 #2): not upgraded

The owner said Quang's C: had been cleaned, but at 20:50 `Get-PSDrive C` (PowerShell through SSH) and `df /mnt/c` both
still showed **6.9 GB free** (155 GB disk). The plan needs ≥ 20 GB before the WSL install, because Quang's earlier I/O
errors happened at this level. Nothing was installed or deleted on Quang. A read-only scan found nothing big in the user
profile (Downloads/Desktop/Documents ≈ 0, Temp 0.19 GB, Recycle Bin 0.05 GB, `C:\ProgramData` 3.9 GB); the WSL disk file was
not under `%LOCALAPPDATA%\Packages` of that user.

## What this does NOT show

- Quang is still on candidate4 (CPU home `heteroes-c3-cpu`) and has no GPU worker; the 3-GPU long run (step 5) cannot start.
- No managed run was started on candidate5; parity with the new agent/backend/web is not re-proven here.
- The Windows quit → relaunch and silent uninstall test on candidate5 is still to do (plan: once before flag day; may be
  after step 5). The Windows Worker was driven through its remote-debugging bridge, not clicked by a person.
- The installer for the one-line command came from a private HTTP server, not from the (unpublished) public download path.
