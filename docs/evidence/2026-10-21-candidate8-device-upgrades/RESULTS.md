# Candidate8 isolated lab and device upgrades (2026-10-21)

Package receipts: `../2026-10-21-r11-candidate8/RESULTS.md`. Transport: private tailnet HTTP on port 8802, serving the
candidate8 Archive directory (restarted from the candidate7 one). The public r10 lab is unchanged. Every existing device
identity is preserved. All five devices run build `lf1-20261021-r11-candidate8`, Worker runtime bundle
`b377c9c94cea…` (desktop apps: their own install directory name).

| Device | Install | Installed source | Self-test | State |
| --- | --- | --- | --- | --- |
| Isolated Lab Server (5070, port 8790) | runtime `7c50fd65810f` | 63 Python files equal source (`lab-server-source-equal.log`) | — | running |
| 5070 Ti Linux desktop | runtime `a3da624b2bde` | `src/` 104 files equal source, fix present | GPU PASS | ONLINE, OFF |
| Thao native Windows 3060 | installer hash = receipt, exit 0; runtime `D:\…\d4f9d665ab09` | `src/` 104 files equal source (`windows-source-equal.log`) | GPU PASS | ONLINE, OFF |
| Thao WSL CLI (CPU coordinator) | `b377c9c94cea`, exit 0 | `src/` 104 files equal source | CPU coordinator PASS | agent stopped (`serve` runs it) |
| GTX 1660 SUPER CLI | `b377c9c94cea`, exit 0 | 104 files equal source | GPU PASS | ONLINE, OFF |
| **Quang WSL 3060 (CLI)** | `b377c9c94cea`, exit 0 (first time on candidate8; from candidate6) | 104 files equal source | GPU PASS (`LD_LIBRARY_PATH=/usr/lib/wsl/lib`) | ONLINE, OFF |

"Equal source" = every installed `*.py` is byte-identical to the repository file (`installed_equals_source.py`, source
tree at commit `437f5ee`). The lab lists all six devices APPROVED with contribution OFF (identity `cli-894b5d440398` for
Quang, `desktop-9f9da13f0f82` for Windows, `cli-3e355c6e9e70` for the 1660S).

## Operator notes and deviations

- **A wrong self-test on the CPU coordinator.** I ran `heteroes-worker selftest` without `--device cpu` on Thao WSL. It ran
  on the GPU and overwrote the `selfTest` in that home's `settings.json`
  (`thao-cpu-selftest-attempt1-wrong-device-cuda.log`). `agent-config.json` still said CPU coordinator. I reran
  `selftest --device cpu` (`thao-cpu-selftest.log`: CPU coordinator, `coordinator-cpu-v3`, in both files). No code or run
  state was touched.
- Thao Windows: `D:\HeteroES-Worker-data\runtimes\81663cebe7eb` (candidate7) is left on disk, unused.
- Quang's C: held 20.0 GB before and after the upgrade (replaced the 4.9 GB candidate6 runtime in place).
- The 1660S agent of candidate7 was stopped by PID before the upgrade; agents on the 1660S and Quang were started again
  with `nohup setsid heteroes-worker run` (logs under `/tmp/heteroes-r11-c8`).

## What this does NOT show

No 50-generation acceptance, outage, join/leave, restart or parity claim. No publication, deployment, merge or push.
