# Local Lab Server

The Lab Server owns accounts, workspaces, the queue, monitoring and verified
recovery storage. It runs on a CPU computer; GPU contributors use the Worker app.
Cloud access is not required for this local release.

## Start a new lab

1. Extract the Linux portable installer and open `heteroes-server`. On Windows,
   use the per-user installer after its native hardware acceptance is completed.
2. Select **Install Server**. The app downloads hash-pinned standalone Python
   and CPU dependencies into its private directory. It does not modify system
   Python, a Conda environment or GPU drivers.
3. Select the LAN or Tailscale address belonging to this computer. Loopback
   (`127.0.0.1`) works only on this computer. Choose an unused port.
4. Choose a disk for checkpoints, and enter the administrator username and a
   password of at least 12 characters. The password is sent privately to the
   bootstrap process; only its Argon2 hash is saved in SQLite.
5. Select **Start Server**, then **Open lab**. Web and API share the shown
   address. Sign in, approve participants, pair and approve workers, then release
   the held queue in Operations when resources are ready.

Startup is manual by default. Closing the window keeps the server in the tray.
Quit stops the owned CPU server process. Workers keep local evidence during API
outages and replay it after reconnection. The optional login-start checkbox
starts this lab when the desktop app launches at login.

The selected Linux volume UUID is checked before storage access. Reconnect the
disk if it is missing; the app does not silently use the root filesystem instead.
Changing a network address or port requires stopping the server and editing its
private configuration for now; the graphical reconfiguration flow is pending.

## Data and diagnostics

The Electron user-data directory contains `lab/config.json`, the signing key,
`lab/state/product.sqlite`, isolated runtimes and `server.log`. Keep this directory
private and on a filesystem suitable for live SQLite and executable runtimes.
Large immutable objects live in the selected storage directory. The signing key
is never stored alongside public installer downloads.

The bootstrap does not overwrite an existing lab or import historical process
records. Use the existing backup/restore guide for migration into a fresh
deployment; hold its queue and review worker configuration before releasing it.

The current Linux proof used an actual portable app and fresh isolated CPU
runtime under Xvfb. Native Windows and a nontechnical owner on a normal desktop
remain acceptance gates. The CPU pilot can run without bundled Worker downloads;
use the separately checksum-identified qualified Worker installer.

## Reproduce a reviewed build

Build the real web UI and the Server workspace. Download the exact CPU wheels
from `backend/requirements.lock.txt` for each target OS; Windows also requires
Colorama 0.4.6. Run `scripts/build-server-profile.py --wheelhouse <directory>`
with `linux/` and `windows/` wheel directories. The generator matches every wheel
to its versioned PyPI filename/hash and writes installer locks and the source/web
bundle, preserving the reviewed standalone Python pins from the Worker profile.

Package with Electron Builder using a fresh output directory. Never replace an
installer referenced by existing evidence. `scripts/check-linux-server.cjs`
requires an actual executable, evidence output and isolated XDG directories.
It verifies the fresh installation, CPU-only dependencies, bootstrap/login,
same-origin routes, held queue, tray behavior, stop and restart.

Current source/deployment status and verification limits: [HANDOFF.md](HANDOFF.md).
