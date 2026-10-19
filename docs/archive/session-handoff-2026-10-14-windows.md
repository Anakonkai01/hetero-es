# Session handoff — 2026-10-14: first real Windows Worker, r8 / r9 / r10

**Read this after** `session-handoff-2026-10-13-ui.md`. Owner rules are unchanged (`AGENTS.md`).

## Outcome
The owner ran the Worker on a real Windows PC (RTX 3060, account "Thao") and got it paired, approved and contributing
(`3060-thao`, platform windows, APPROVED, enabled, seen seconds ago, checked read-only on the lab database). First native Windows device on the lab.

## What went wrong on the way (and what fixed it)
| Symptom on Windows | Real cause | Fix |
| --- | --- | --- |
| "Enable contribution" fails, `AGENT_UNAVAILABLE`; Connection check: coordinator red | A dead agent process was kept as "ownership unknown" (never restarted, Enable locked); stderr and exit status were thrown away | r8: bridge records spawn error / exit code / stderr tail; dead agent released; one sanitised log entry per cause; Enable retries; 30 s back-off |
| Sign-in: `LAB_UNREACHABLE`, then `LAB_TIMEOUT`; lab address fixed at `100.118.x.x` | A stale pairing from an earlier test pointed at a Tailscale address; the owner had turned Tailscale off. `%APPDATA%\@heteroes` had not been deleted and the old uninstall kept it. The paired view had no way to change lab | r9: network errors named (`LAB_DNS_FAILED`, `LAB_CERTIFICATE_REJECTED`, ...). r10: "Forget this pairing" (local, works offline, refuses while ON), `OLD_LAB_UNREACHABLE`, Worker uninstall deletes its data (not on in-place upgrade, never for the Lab Server) |
| Approve device: "Owner must belong to target workspace" | The device owner (`thaonguyen`) was in no workspace; an invitation was pending and has to be **accepted by the invited user** | Explained in the UI (vi/en). No data was changed by the AI |
| Revoked devices stay in the list | The backend had no removal | r10: `DELETE /api/v1/platform/devices/{id}` (admin; revoked or pending only; audited), revoked hidden by default, "Remove from list" |

## State at the end
- Branch `feat/local-first-lf1`, nothing pushed. Live lab runs the r10 backend and web (restart through `local-lab.py restart`, lab was idle); download page offers **r10**. r5..r9 files stay on the Archive disk. `/etc/fstab` now has the Archive line (the owner added it); the lab came back about 6 minutes after the 12:53 reboot because the user unit retries every 30 s until the disk is mounted.
- Evidence: `docs/evidence/2026-10-14-r8/`, `-r9/`, `-r10/` (each README says what it does NOT show).
- Not shown: the r10 screens ("Forget this pairing", device removal controls) were not clicked on a real machine; the uninstall was verified in Wine (renamed PowerShell stub), not in Windows Settings.

## Lessons
- Do not swallow errors in the Worker: every user-facing failure needs a specific code and one log line (host and cause only, never a body or token).
- A `--prepare-only` / build never replaces an existing build name: if a check fails after the build started, fix the probe and re-run the check; only rebuild (new name) when shipped code changed.
- `npx @electron/asar extract-file` writes into the **current directory**: it overwrote the repo `package.json` once (restored from git). Run it from a scratch directory.
- Wine's PowerShell stub always says "app is running", so the NSIS installer cannot run silently in a stock prefix; rename the stub in a scratch prefix to test installs.
- Electron `net.fetch` error shape (checked on Linux): `Error: net::ERR_*` message, no `cause.code`. If Node `fetch` ever needs replacing by `net.fetch` (system proxy / certificate store), `networkCode()` must learn `net::ERR_NAME_NOT_RESOLVED`, `ERR_CONNECTION_REFUSED`, `ERR_CERT_*`, etc.

## Next steps
1. Installer polish (**`docs/plan-installer-polish.md`**, not started; the owner chose to do it next session): brand assets (the web favicon is still the Vite logo, the Worker icon is a flat "H"), wizard installer (owner chose the step-by-step wizard, vi + en), no code signing yet (guide + SHA-256 on the download page), Windows file metadata.
2. Owner: confirm the 8-character password minimum; look at presentation mode.
3. A second real GPU in a run (the 3060 is now online): rehearse the 20/11 demo with it, only with the owner's go and `--gpu` + `HETEROES_GPU_ACCEPTANCE=1`.
