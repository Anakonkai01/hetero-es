# Worker desktop: private M3a trial

The Worker is a private installer candidate. Native Windows GPU compatibility and
an actual Windows–Linux distributed run still require hardware acceptance. The
existing M1 deployment is separate; this build connects to the local M2 lab.

## Owner workflow

1. On Windows 11 x64, install the private `HeteroES Worker Setup 0.1.0.exe`
   for your user. On Linux x64, download the portable archive, extract it through
   the file manager and open `heteroes-worker` (enable execution in Properties
   if needed). The optional AppImage needs FUSE 2; on desktops without FUSE 2,
   use the portable archive. This machine has no FUSE 2, so the packaged binary
   was tested directly. No repository, Python or WSL
   installation is required. Linux needs a working desktop keyring for device
   credential storage.
2. Install Tailscale using its graphical installer, sign in and join the lab's
   network. Ask the lab administrator for network access if needed.
3. Enter the local M2 lab address `http://100.110.165.40:8002`, then sign in with
   your own lab account. Account approval and device approval are separate.
4. Select **Install isolated runtime**. Setup downloads pinned Python 3.12.15,
   target-specific wheels and the pinned Qwen model into application data. It
   verifies sizes/SHA-256, retains partial downloads and checks free disk space
   before installation. Internet access is required for this first step.
5. Select **Run compatibility check**. This deliberately repeats one GPU candidate twice plus a seed-0 prediction probe
   under the FP32/canonical CPU-noise profile and checks repeated observations,
   recipe, perturbed weights, reward and exact restore against the Linux reference. The extra probe compares all
   16 answer texts and reward with preserved Linux GPU evidence.
   CUDA discovery alone cannot pass admission. Keep contribution OFF on failure;
   export diagnostics and send the report to the project operator.
6. Name and pair the device. Pairing consumes a one-use, ten-minute code from
   your authenticated lab account. An administrator approves the device on the
   website's Operations page and selects the workspace.
7. Enable contribution only when you intend to share the GPU. The local M2
   review queue is deliberately held until the operator starts the approved
   hardware campaign. The Windows app is worker-only; the Linux coordinator
   remains the existing 5070 Ti machine.
8. Closing the window keeps the app in the tray. Before returning or shutting
   down a computer, choose **Stop safely**, wait until work is confirmed stopped,
   then **Quit safely**. Unknown process identity keeps ownership reserved. Every
   application/agent restart begins OFF; there are no automatic updates.

Windows may display an unsigned private-installer prompt. This build has no code
signing certificate and is not claimed to pass SmartScreen reputation checks.
If Windows reports missing runtime DLLs, use the app's Microsoft Visual C++ x64
runtime link; it does not change the NVIDIA driver. Driver incompatibility must
be diagnosed separately rather than changing the numerical contract.

## First hardware acceptance (2026-10-11)

Use one native Windows GPU with its owner's agreement. Record OS, driver, GPU,
installer SHA-256 and self-test diagnostics. Check a second application instance,
restart-OFF, close-to-tray, one-use pairing, admin approval and owner-only ON.
After the self-test passes, the operator may run a short actual distributed
experiment with the existing Linux coordinator and compare reward/update/final
hashes to the canonical baseline. Keep GPU time within the M3a 0.25-hour campaign
cap and the original 2-hour cumulative budget. The prior cumulative usage was
1.028929731 GPU-hours after the recorded unintended local run; preserve the separate 0.083799-hour M2 cloud allowance.

Test OFF and Quit during a candidate, a network outage, a coordinator outage and
an app restart. Confirm cooperative restore/submission, no duplicate process,
and no resource release while process state is unknown. Record failures as
failures; Wine execution is not native Windows GPU evidence.

## Operator/developer build

From this repository root, use `npm ci`, then `npm run build:web`,
`npm run build:worker`, `npm run test:worker`. The single root lockfile owns all
workspaces; do not run a separate install inside `frontend`.

The runtime profile generator takes Track A sources and reviewed target-specific
pip reports: `python scripts/build-worker-profile.py --track-a
../hetero-es-m3-runtime --reports <reports-directory>`. `pip --platform` alone does
not evaluate Windows PEP 508 markers; the Windows report must be resolved with
Windows markers or on Windows. The committed manifests and requirement locks
include every wheel's exact hash. NVIDIA mirror artifacts are switched to their
identical-hash official PyPI files when available.

Build AppImage with `npm run pack:linux --workspace @heteroes/worker`; build NSIS
with `npm run pack:windows --workspace @heteroes/worker`. Cross-building NSIS on
Linux uses Wine. Build outputs stay in the ignored `desktop/worker/release`
directory. Check SHA-256 before sharing a private installer. Do not upload
credentials, runtime state or diagnostics without reviewing their contents.

The private Windows installer is unsigned and per-user with elevation disabled.
Download buttons are in the Workers page; SHA-256 is in
`docs/evidence/2026-10-10-m3/installers.json`. The Linux portable archive is built
from the same packaged app as the AppImage and needs no FUSE mount.

The M3 web preview is `http://100.110.165.40:5181`, using real M2 data with dispatch
held. The existing M1 website at port 5173 is unchanged.

After a host reboot, run `python3 scripts/start-m3-preview.py` from this checkout
to reopen the local M3 preview. It requires the existing private M2 configuration
and backend environment, verifies the dispatch hold, and starts only the CPU API
and web server. It does not start compute agents or configure automatic startup.
