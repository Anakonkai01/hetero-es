# Candidate7 isolated lab and device upgrades (2026-10-21)

Package receipts: `../2026-10-21-r11-candidate7/RESULTS.md`. Transport: private tailnet HTTP on port 8802, serving the
candidate7 Archive directory. The public r10 lab is unchanged. Every existing device identity is preserved.

| Device | Install | Installed source | Self-test | State |
| --- | --- | --- | --- | --- |
| Isolated Lab Server (5070, port 8790) | runtime `5134be3d236e` | `backend/` equals source | — | running |
| 5070 Ti Linux desktop | runtime `0aa6889b70d3` | `src/` equals source | GPU PASS | OFF |
| Thao native Windows 3060 | installer hash = receipt, exit 0; runtime `D:\…\81663cebe7eb` | `src/` equals source | GPU PASS (first try) | OFF |
| Thao WSL CLI (CPU coordinator) | `57b0faf6d31a`, exit 0 | `src/` equals source | CPU coordinator PASS | agent stopped |
| GTX 1660 SUPER CLI | `57b0faf6d31a`, exit 0 | `src/` equals source | GPU PASS | **new in this lab**: paired, approved, OFF, agent stopped |
| Quang WSL 3060 | not done | — | — | offline (Tailscale offline, SSH timeout) |

"Equals source" means the SHA256 of every installed `heteroes/**/*.py` (sorted, `LC_ALL=C`) equals the repository's
`runtime/src` at `63d9b0a`. Installed `membership.py` `d99f847c…`, `cpu_guard.py` `150ac9fd…` (unchanged from
candidate6). The 1660S is `cli-3e355c6e9e70` / device `33c70b2277c14eaca81b6645fcb3ca4d`, same workspace as the others.

Both desktops reported `approvalStatus: PENDING` locally right after the upgrade; the lab lists all devices APPROVED.

## Disk cleanup (owner: "có những cái ko cần thiết thì xoá đi")

Removed only superseded, reproducible software caches and disposable check trees; no run ledgers, artifacts,
credentials or evidence.

- 5070 system disk 11 GB → 45 GB free: `.scratch/r11-builds`, `.scratch/r11-packaged*`, candidate4/5 and
  `system-finish` packaging-check trees, `r11c3/c4-server`, the candidate3–6 desktop runtimes and old server runtimes
  of the isolated lab. Their receipts were already in `docs/evidence/`.
- Thao Windows D:: the candidate5 and candidate6 runtimes (not in use; checked by process path).
- Thao WSL: the unused `sysfinish-q1` CLI home `~/.local/share/heteroes-worker` (no device identity).

## Operator notes

- The Windows launch control still hangs after the app starts (PowerShell keeps the session open); the app runs and
  `launch-result.json` is written. The driver now guards `typeof process` before reading `process.mainModule`.
- Thao Windows rebooted at 11:10 today, so the Worker was not running before the upgrade.

## What this does NOT show

Four of five devices, not all. No 50-generation acceptance, outage, join/leave or parity claim. No publication,
deployment, merge or push.
