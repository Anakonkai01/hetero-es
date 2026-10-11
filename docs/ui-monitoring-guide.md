# Web and desktop UI — 2026-10-11

The current priority is the owner's comprehensive Web/Worker/Server UI request.
Light, dark and system themes remain available, with Vietnamese/English and
teal/blue/violet accents. Cloud remains deferred.

## What is available

- `/` is a public homepage with workflow information, actual API reachability,
  sign-in/account links and downloads for both desktop apps. Its topology diagram
  is explicitly an illustration, not a claim about currently connected devices.
- Login/register have a dedicated layout, labeled fields, password visibility
  on login, sending/error states and appearance controls.
- Dashboard shows scoped experiments, queue/hold state, GPU connectivity,
  contribution and allocation independently. GPU counts and fresh GPU watts
  deduplicate known physical UUIDs. Recent events show the newest timestamps.
- Workers has separate fleet and owner-device views. Fleet cards show measured
  hardware data, with expandable host/storage/network details. Device details
  show full telemetry. Qualification throughput is labeled separately from live
  usage; capacity remains visible when a device is offline.
- Experiment cards and detail show generation progress, candidates per generation,
  participating workers and per-candidate seed strategy. The generation selector
  exposes actual candidate IDs, seeds, acceptance states, assigned workers and
  rewards, with links to full generation/candidate/attempt history. Retries reuse
  the same deterministic seed. There is no invented editable global base seed.
- Reward charts use ledger results. Held-out validation/test metrics are marked
  unavailable for existing built-in-workload runs. Checkpoint status and artifact
  downloads use actual API data; mock downloads remain labeled as demonstrations.
- Worker shows setup stages, approval/contribution, physical GPU identity,
  assignment epochs/process ownership/readiness, lab connection and telemetry.
  Detailed generation/candidate/seed history opens in the lab website. Unknown
  ownership and draining states block a new contribution request.
- Lab Server shows its setup stages, network/storage/account choices, service
  address, manual start/stop, optional autostart and measured CPU/RAM/disk data.

## Measurements and limits

The Agent samples without importing Torch or opening a CUDA context. GPU readings
use `nvidia-smi`, matched to the qualified physical UUID. Unsupported readings
remain unavailable. Linux host readings use `/proc`; Windows CPU/RAM use a fixed
CIM query. Capacity readings cover the state and configured artifact filesystems.
Linux network rates include all non-loopback interfaces, so tunnels can count
the same traffic more than once; disk rates include whole physical block devices.
Windows host network/disk I/O rates and CPU temperature/power are not implemented.

Samples are cached for ten seconds. Web observations are marked old after thirty
seconds or when the device is offline. API history keeps at most 180 points per
device and returns the most recent 60; the desktop Agent keeps 60 in memory.
The chart allows GPU power/temperature/utilization and CPU utilization selection,
uses real timestamps and does not draw across gaps over thirty seconds.

GPU energy is an estimate integrating successive watts samples over intervals
of at most thirty seconds. It resets with the Agent session and reports sampled
coverage. It includes unrelated activity on this physical GPU and excludes CPU
and whole-computer power. It is not experiment energy accounting or billing.

Telemetry is capability-negotiated: the first poll uses the original protocol,
and observation fields are sent only after the Server advertises support. A
missing GPU sensor does not hide available host or disk measurements. Device
tokens remain private; telemetry cannot change contribution or GPU admission.

## Running local preview

Web: `http://100.110.165.40:5181/`. CPU API: port 8002. It uses the existing
private `~/.config/heteroes-m2` configuration and ext4 SQLite. The live cutover
preserved all 21 historical experiment bodies/snapshots, device owner flags and
the held queue, with no reservations. Private pre-cutover/migration/reload
snapshots are under `~/.config/heteroes-private/ui-review`. Existing live recovery
storage is still unconfigured (`storageMode: none`); the redesigned UI does not
claim those historical runs now have a configured local checkpoint service.
Fresh Lab Server installs configure local storage during setup.

One local Agent supplies real 5070 Ti readings while contribution is OFF:

- Configuration/PID birth record/log: `~/.config/heteroes-private/ui-local-agent`.
- State: `~/.local/share/heteroes-ui-local-agent`, isolated from historical Agent
  process reports. It reuses the enrolled local `5070ti` identity, not a new alias.
- Source: Track A `/home/pc5070ti/projects/hetero-es-m3-runtime`, commit `0fb8e16`.
- Python: existing `~/miniforge3/envs/heteroes-match/bin/python`.
- Never run this Agent alongside another Agent owning the same device. To stop
  it, verify the saved PID's `/proc/<pid>/stat` start-time identity before signaling
  that PID. A new boot starts OFF. Do not replay the old Agent state directory.

After reboot, first verify Archive-2tb UUID `10443D1F443D094C` is mounted at
`/mnt/Archive-2tb`; do not create artifact/download directories on root as a
fallback. Do not use `/mnt/sekai`. Run `python3 scripts/start-m3-preview.py` to
start the held preview. It checks held dispatch and refuses an untracked listener.
The monitoring Agent starts separately with `PYTHONPATH=<Track A>/src` and
`python -m heteroes.product.agent run --config <private config path>`, after
confirming the prior tracked Agent is stopped. Credentials stay outside Git.

## Builds and evidence

The homepage serves build `ui-20261011-r2`: Linux portable archives and Windows
per-user NSIS installers for Worker and Lab Server. Full HTTP sizes/hashes match
the [installer receipt](evidence/2026-10-11-ui/installers.json). Files are on
Archive-2tb under `heteroes-local/downloads/ui-20261011/{worker,server}`; generated
public symlinks and manifest are ignored by Git. Older accepted installers remain.

Build Web and both desktop workspaces, refresh source bundles with
`scripts/refresh-worker-runtime.py --track-a <Track A>` and
`scripts/refresh-server-runtime.py`, then package into staging directories with
Electron Builder. Source refresh preserves Python/wheel/model pins. Use
`scripts/publish-local-installers.py --packages <staging root> --build <new name>`
to prepare dated local downloads; it verifies the storage UUID and refuses
replacement of immutable bundles. Restoring this deployment also requires
recreating public links and `manifest.json` from the installer receipt.

See [UI evidence](evidence/2026-10-11-ui/README.md). Published Linux archives were
extracted and opened in real Electron under Xvfb, in both themes. The new Server
also passed fresh CPU installation/bootstrap/same-origin/tray/stop/restart.
Windows installers were built, but this new UI has not been executed on native
Windows; the older Windows numerical proof remains historical. A normal desktop
owner walkthrough and real GPU pause/resume remain pending. No new GPU workload,
cloud job, push, merge or tag was performed for this UI work.
