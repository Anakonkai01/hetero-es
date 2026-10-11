# M3a: native Worker and shared product UX

Accepted 2026-10-10; implementation prepared locally on 2026-10-10/11. This is a
private installer trial, not completed native Windows hardware acceptance.
Cloud acceptance remains pending independently; no cloud accounts are required.

## Decisions and delivered behavior

Worker-first Windows 11 x64 native and Linux x64, existing CPU server and
Tailscale graphical setup. Windows is worker-only; the existing Linux 5070 Ti
coordinator retains the ledger and numerical implementation. No Lab Server
installer, parallel scheduler or additional model/dataset was added.

Electron/React desktop has connect/login/setup/qualification/pair/approval/owner
contribution, tray close, safe OFF/Quit and redacted diagnostics. Every agent boot
starts OFF; Windows uses a process-birth-bound cooperative stop marker and kernel
instance lock. Unreadable identity is unknown and holds resources. Quit fences
late enable commands while sending a final confirmed observation when possible.
Credentials use Electron safeStorage; Linux plaintext fallback is rejected.

The private per-user Windows NSIS installer disables elevation. Linux has an
AppImage and a portable archive for desktops without FUSE 2. Python 3.12.15,
pinned platform-specific wheels and Qwen revision
`7ae557604adf67be50417f59c2c2f167def9a775` download on first setup with size/SHA-256,
resume, disk preflight and offline wheel installation. The installer carries
runtime sources/reference/manifests, not model weights or device credentials.
The exact runtime source archive and each downloadable artifact are hashed.

Web and desktop share bundled IBM Plex fonts, Vi/En, light/dark/system and
teal/blue/violet preferences without resetting forms. Core web workflows were
restyled; experiment setup has three steps. Real mode uses health and committed
candidate counts. Agent mode hides conflicting legacy contribution controls;
unknown shutdown is not presented as confirmed stopped. Pairing codes are
single-use, ten minutes, with copy/countdown and separate administrator approval.

## Verification and limits

- Track A CPU suite: **2041 passed, 100 skipped**, CUDA hidden. Scratch mutation
  ignoring birth identity is caught by the stop regression.
- Backend: **73 passed**. Desktop downloader/lifecycle/archive: **11 passed**.
- Independent MSW domain suite: **22 behavior groups passed**.
- Real M2 server browser: login/workspace/workers/create/monitor/list/operations/
  profile at 375/768/1440 and 200% zoom, locale form preservation and persistent
  theme. Both languages were exercised. Keyboard/reduced motion and 4.5:1 minimum
  core text/status token contrast pass for all six light/dark accent palettes.
- Actual Electron main/preload/renderer and packaged Linux binary: sandboxed
  IPC, denied arbitrary commands, real lab login, tray close, responsive UI.
- Fresh isolated Linux runtime downloaded/installed successfully; CPU imports
  verify Python 3.12.15, torch 2.13.0+cu132, NumPy 2.5.3, transformers 5.17.0,
  tokenizers 0.23.2, safetensors 0.8.0. CUDA was hidden. This proof used the initial
  source profile; the final archive adds the separately tested Quit fence and 16-answer prediction gate.
- Wine bootstrap: verified Windows standalone Python, real Win32 process birth
  and msvcrt lock under emulation. This is **not native Windows GPU evidence**.
- Installer files built; Windows Authenticode absent as expected for a private
  unsigned trial. All-dependency and production npm audits report zero findings.

Evidence and SHA-256: [evidence folder](evidence/2026-10-10-m3/README.md),
[installers](evidence/2026-10-10-m3/installers.json),
[owner guide](worker-desktop-guide.md). Hardware gates remain: fresh native
Windows install without Python/repo/WSL, repeated GPU candidate/reference match,
actual Windows-worker/Linux-coordinator run and outage/restart/stop trials.
Do not claim post-training quality or broad Windows numerical portability.

## Current local deployment

A worktree `../hetero-es-m3-runtime`, branch `feat/m3-native-worker`; B worktree
`Hetero-ES-LLM-m3`, branch `feat/m3-worker-desktop-ux`. Local commits only.
Track A runtime source commit: `9ef0d91`.
Original M1/M2 source checkouts remain clean. M1 UI source remains unchanged.
M3 preview is `http://100.110.165.40:5181`; local API is
`http://100.110.165.40:8002`. Admin uses the previously requested local password.

The held M2 CPU backend now loads M3 routes, including native qualification
validation and the UI address for the desktop's Open lab website action. A
consistent pre-cutover SQLite backup is outside Git; all 19 existing experiment
bodies were preserved. Dispatch remains held, no queue or reservations. Worker
installers are downloadable privately through the Workers page. Returned 3060
machines were not contacted or selected during this work.

After the host reboot on 11/10, only the M3 CPU API and preview were restarted;
M1 services and compute agents remain stopped. The real-server browser checks
passed again; the three installer checksums and HTTP range downloads were
verified. `scripts/start-m3-preview.py` provides an idempotent manual restart,
requiring the existing dispatch hold. See `post-reboot.json` in the evidence.

## Recorded unintended run and GPU budget

The intended overnight checks were CPU-only. A legacy integration-test command
was accidentally invoked and submitted one generation on the local 5070 Ti:
`45d72973ddf243fdb8d9a46d2e9a670f`. It was interrupted and cooperatively cancelled;
owned worker death confirmed, zero queue/reservations and empty CUDA process query.
It is not M3 native acceptance. The default script now observes only; GPU actions
require an explicit flag plus environment opt-in.

Conservative additional usage: 0.007097731 GPU-hours, cumulative **1.028929731**
of the original 2.0. Deduct this from M3a's 0.25-hour first campaign allowance;
preserve M2's remaining 0.083799 for cloud. The owner hardware trial is next.
