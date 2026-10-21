# Candidate9 isolated lab and device upgrades (2026-10-21)

Package receipts: `../2026-10-21-r11-candidate9/`. Transport: private tailnet HTTP on port 8802 serving the candidate9
Archive directory. The public r10 lab is unchanged. Every existing device identity is preserved. All devices run build
`lf1-20261021-r11-candidate9`, Worker runtime bundle `9a553d2dfae9…` (desktop apps: their own install directory name).

| Device | Install | Installed source | Self-test | State |
| --- | --- | --- | --- | --- |
| Isolated Lab Server (5070, port 8790) | runtime `37eb126524bb` | 63 Python files equal source (checked in the earlier session, no log kept) | — | running |
| 5070 Ti Linux desktop | app restarted from the candidate9 unpacked build, runtime install READY | built from the same bundle as the Linux package checks | GPU PASS (`worker5070/results.jsonl`, 11:03Z) | ONLINE, OFF |
| Thao native Windows 3060 | installer hash `e9f1f4c7…` = receipt, exit 0; runtime `D:\HeteroES-Worker-data\runtimes\29c6db0c83bb` | `src/` 104 files, tree hash equals repo (`windows-source-equal.log`) | GPU PASS (`windows-selftest.log`) | ONLINE, OFF |
| Thao WSL CLI (CPU coordinator) | `9a553d2dfae9` | `src/` 104 files, tree hash equals repo | CPU coordinator PASS | agent stopped (`serve` runs it) |
| GTX 1660 SUPER CLI | `9a553d2dfae9` | 104 files, tree hash equals repo | GPU PASS | ONLINE (agent started 17:5x), OFF |
| **Quang WSL 3060 (CLI)** | `9a553d2dfae9`, exit 0 (from `b377c9c94cea`) | 104 files, tree hash `b8e92142…` equals repo (`quang-source-equal.log`) | GPU PASS (`LD_LIBRARY_PATH=/usr/lib/wsl/lib`, `quang-selftest.log`) | ONLINE, OFF |

Tree hash = `tree_hash.py` over every `*.py` of `src/` (104 files, `b8e921426f58…`). The lab lists the devices APPROVED with
contribution OFF (read from the API at the end of this session; 4 ONLINE).

## Operator notes and deviations

- The 5070 desktop app hit the known 30 s Electron cold-launch timeout on the first start (`app-c9` first attempt); a second
  start worked.
- Windows: `install` and `selftest` first failed with `DEBUG_ENDPOINT_NOT_READY` because the app was not running (the
  driver talks to a running app). The `launch-c9.ps1` driver then reported "Execution context was destroyed" and left its
  PowerShell wrapper hanging (`windows-launch.log` is empty), but the app was up with build candidate9; I ended the
  wrapper process on the 5070 and ran `install` and `selftest` again: both exit 0. No code was changed.
- Quang's C: held 19.6 GB after the upgrade (replaced the 5.1 GB runtime in place). Quang came back online at the owner's
  request around 17:30.
- Agents on the 1660S and Quang were started with `nohup setsid heteroes-worker run` (logs under `/tmp/heteroes-r11-c9`).

## What this does NOT show

No acceptance run, no restart or parity claim. No publication, deployment, merge or push.
