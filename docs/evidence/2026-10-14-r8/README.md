# Evidence 2026-10-14 — Worker r8: make the Windows agent failure visible

Build `lf1-20261014-r8` (Worker + Lab Server, Windows and Linux) is on the download page of https://lab.heteroes.site.
r7 and earlier files stay on the Archive disk; only the manifest points at r8. Backend and web are unchanged from r7.

## Why
The owner ran Worker r7 on a real Windows PC: sign-in worked, "Enable contribution" failed with `AGENT_UNAVAILABLE`, and
Connection check showed the coordinator step red. The cause was invisible: a dead agent was kept as "ownership unknown"
(so it was never restarted and Enable stayed locked), and stderr / exit status were thrown away.

## What changed (desktop/worker)
- `bridge.cjs`: spawn error, exit code / signal and a 4 KB stderr tail are recorded; calls fail with `AGENT_SPAWN_FAILED`,
  `AGENT_EXITED` or `WINDOWS_RUNTIME_MISSING` (also from Windows exit codes 0xC0000135 / 0xC000007B).
- `service.cjs`: a dead agent is released; one log entry per distinct cause; automatic retries at most every 30 s; Enable
  retries at once and returns the real code; the Connection check names the code for the coordinator step.
- `log.cjs`: `detail()` writes a sanitised tail (home path removed, Bearer values and 32+ character strings redacted, 20 lines).
- `main.tsx`, `translations.ts`: plain vi/en sentences, a warning panel with the code, the "Install Windows runtime" button.
- Start-up now logs the lab host (host only) and whether a device is paired, to explain the `100.118.x.x` address the owner saw.

## Files
| File | Shows |
| --- | --- |
| `checks/` | `scripts/check-all.sh`: ALL PASS (backend, frontend, Worker 65 tests incl. 11 new in `agent-failure.test.cjs`, types, lint, i18n, builds, six browser/Electron probes on throwaway fixture labs). |
| `worker-packaged-linux/`, `worker-station-packaged-linux/` | The packaged Linux Worker driven by the onboarding and station probes. |
| `installers-r8.json`, `installers-r8-published.json` | Sizes and SHA-256 of the four installers, prepared then published. |
| `public-verify.json` | Read-only check over HTTPS: pages, all four installers downloaded and matching size + SHA-256, `allOk: true`. |

A scratch mutation check (13 mutants: keep the dead bridge, log every time, no back-off, no retry on Enable, stderr not kept,
spawn code lost, redaction removed, ...) killed all 13.

## What this does NOT show
- Nothing ran on Windows. r8 was built through Wine; the apps were exercised on Linux only.
- It does not fix the Windows failure. It makes the cause readable (`worker.log`, the code in the app). The real cause
  may still be in the Windows runtime and would be fixed in r9 once the owner's log is read.
- The meaning of the `100.118.x.x` address is still unknown (probably a saved lab address); no change was made for it.
