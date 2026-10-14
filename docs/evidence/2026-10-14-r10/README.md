# Evidence 2026-10-14 — r10: a way out of a dead pairing, clean uninstall, removable devices

Build `lf1-20261014-r10` (Worker + Lab Server, Windows and Linux) is on the download page of https://lab.heteroes.site.
The backend and the web were also redeployed (backend restart through `scripts/local-lab.py restart` while the lab was idle:
no runs, no GPU reservations; web swapped from `frontend/dist.new`). r9 and older files stay on the Archive disk.

## Why (the owner's Windows report)
1. The app stayed paired to an old Tailscale address (`100.118.x.x`). With Tailscale off, every request timed out and
   "Change lab" could not leave it. The only way out was deleting `%APPDATA%\@heteroes` by hand.
2. Uninstalling the app kept that folder (`deleteAppDataOnUninstall: false`), so a re-install brought the stale pairing back.
3. Approving the new 3060 failed with "Owner must belong to target workspace": the owner account was in no workspace.
4. Revoked devices stayed in the list forever; the backend had no way to remove one.

## What changed
- Worker: `Service.forgetDevice()` + a "Forget this pairing" button (sign-in panel and Lab connection panel, with a
  confirmation). Local only, works with no network, refuses while contribution is ON, removes the stored credential, sets the
  old agent state aside (`agent-state.forgotten-<time>`), keeps the GPU compatibility result. Changing lab while the old
  address is dead now says `OLD_LAB_UNREACHABLE` instead of a bare timeout.
- Worker installer: `deleteAppDataOnUninstall: true` + `desktop/worker/build/installer.nsh` (removes `%APPDATA%\@heteroes\worker`
  and the parent folder only when empty; skipped for an in-place upgrade). The Lab Server installer is unchanged: its data is the lab database.
- Backend: `DELETE /api/v1/platform/devices/{id}` (administrator only; revoked or pending devices only; refuses approved,
  quarantined or reserved ones; clears the device's command / telemetry / report rows and the worker alias; writes `DEVICE_REMOVED` to the audit log).
- Web: revoked devices hidden by default with "Show revoked devices (n)", "Remove from list" / "Decline and remove", and plain
  vi/en explanations for the lab's English errors (the workspace one says: add the owner to the workspace first).

## Files
| File | Shows |
| --- | --- |
| `checks/` | `scripts/check-all.sh`: ALL PASS (backend incl. 9 new device-removal tests, frontend 74, Worker 78, types, lint, i18n, builds, six probes on throwaway labs). |
| `worker-packaged-linux/`, `worker-station-packaged-linux/` | The packaged Linux Worker driven by the onboarding and station probes. |
| `installers-r10.json`, `installers-r10-published.json` | Sizes and SHA-256 of the four installers, prepared then published. |
| `public-verify.json` | Read-only check over HTTPS: pages, all installers downloaded and matching size + SHA-256, `allOk: true`. |

Scratch mutation checks: Worker forget + installer config 10/10 killed, backend removal 8/8, device list 5/5 (two survivors on the
first backend run, an equivalent message branch and a missing non-admin test, led to two stronger tests).

## The uninstall was run for real, in Wine
Fresh Wine prefix, the r10 Worker NSIS installer, silent install, then fake data in `%APPDATA%\@heteroes\worker` (and one run
with a fake `@heteroes\server` next to it): (a) installing over the existing install with `--updated` kept all data; (b) the
uninstaller removed the program and `@heteroes\worker` and **kept** `@heteroes\server`; (c) with nothing else present it also
removed `@heteroes`. Wine's PowerShell stub always reports "app is running", so for these runs the stub was renamed in the
scratch prefix. This is a Wine run, not Windows.

## What this does NOT show
- Nothing ran on real Windows (r10 included). The Wine run proves the uninstall script's logic, not Windows Settings > Apps.
- `OLD_LAB_UNREACHABLE` and the "Forget this pairing" screens were exercised by unit tests and the Linux probes, not on the owner's PC.
- The new Devices-page controls were checked by unit tests and type/lint/i18n, not by clicking them on the live lab.
- The 3060 owner "Thao" still has to be added to the workspace by an administrator before the device can be approved (no live data was changed).
