# Resource monitoring decisions

This revision applies established monitoring patterns to HeteroES without adding
an external monitoring service or a GPU workload. It retains both themes, English
and Vietnamese, and independent connectivity/contribution/allocation states.

| Reference | Pattern adopted here | Scope |
| --- | --- | --- |
| [Windows Task Manager](https://learn.microsoft.com/en-us/troubleshoot/windows-server/support-tools/support-tools-task-manager) | Overview vs performance/process detail, current readings with units | Host CPU is averaged across logical CPUs; process CPU has its own explicit denominator |
| [GNOME System Monitor](https://help.gnome.org/gnome-system-monitor/) | CPU, memory, filesystems and processes as separate resource groups | Available RAM is distinguished from cache, buffers and swap |
| [btop](https://github.com/aristocratos/btop) | Per-thread load, frequency, host sensors, network interfaces, physical disk I/O, process sorting/filtering | Linux `/proc` and hwmon; bounded top 20 processes, no command lines or environments |
| [nvitop](https://nvitop.readthedocs.io/en/stable/) and [NVIDIA SMI](https://docs.nvidia.com/deploy/nvidia-smi/index.html) | Physical GPU identity, VRAM, controller activity, clocks, fan, performance state, PCIe link and compute processes | Qualified GPU UUID; unsupported optional driver fields cannot discard primary readings |
| [W&B automatic system metrics](https://docs.wandb.ai/guides/track/log/) | Time-aligned resource trends alongside actual experiment/generation/candidate/seed records | Local API observations; no W&B SDK, cloud upload or fabricated run energy attribution |
| [Prometheus node exporter](https://prometheus.io/docs/guides/node-exporter/) | Host/component identities, counters vs rates, freshness and source availability | Fleet sums deduplicate CPU package IDs and GPU UUIDs; missing readings stay unavailable |
| [HWMonitor](https://www.cpuid.com/softwares/hwmonitor.html) and [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) | Sensor provenance and hardware-dependent coverage | No assumption that every CPU, PSU or OS exposes the same sensors |

These are design choices inferred from the referenced tools, not a claim of
feature parity. Detail expands the resource panel, while Overview keeps component
energy rows behind a disclosure. Larger labels, flexible metric grids and a saved
Large text preference replace the previous dense cards. All metric CSS is scoped
to telemetry classes to avoid collisions with other page definition lists.

## Power and persistent energy

On this Linux i7-14700KF, Intel RAPL exposes package and nested core energy. The
[Linux powercap documentation](https://www.kernel.org/doc/html/latest/power/powercap/powercap.html)
defines domains and energy counters. CPU watts come from counter deltas; GPU
watts come from the driver and energy integrates successive samples. These are
hardware/driver observations, not a calibrated wall electricity meter.

CPU package already includes its nested core domain. Detail displays core energy
but excludes it from totals. Independent DRAM domains, when available, can join
the component subtotal. This machine has no separate DRAM power counter. GPU
scope is the selected physical card, not necessarily all cards in a multi-GPU
host. Unmeasured motherboard, RAM, disk, fan and PSU losses are never invented.

Whole-machine AC is a separate meter scope. Without a verified external input,
it is unavailable rather than CPU + GPU. A supported PSU/UPS/wall-meter bridge
may atomically publish `~/.config/heteroes-power/wall-meter.json` with:

```json
{"hostId":"<32 hex characters from telemetry.power.hostId>","scope":"whole-machine-ac","sampledAt":1791720000,"watts":150,"source":"<actual meter name>"}
```

The example is a contract, not a measurement. The bridge must refresh from an
actual device; stale (>15 seconds), wrong-host, wrong-scope or invalid values are
ignored. There is no bridge configured on the current host and no network URL
execution or user-controlled shell command in this input path.

The same OS user's Worker and Server monitors share private SQLite at
`~/.local/share/heteroes-power/energy.sqlite` (directory 0700, database 0600).
Hardware identity and OS boot/monotonic time prevent overlapping aliases from
counting the same interval twice. Persisted totals survive monitor restarts;
Session describes the current monitor, not an experiment. Day and month use the
host's local calendar/timezone; lifetime begins at the first recorded sample.
There is no historical backfill before monitoring was installed. Coverage is
reported per component. Known missing readings, reboot/counter resets, backwards
clock changes and gaps over 30 seconds are not extrapolated. This is not billing.

## Unprivileged collection and platform support

Workers and Server remain unprivileged. This host's RAPL files require root read
permission, so a small fixed publisher reads counters every two seconds and
writes `/run/heteroes-power/rapl.json`. It does not change power limits or drivers.
Source in Track A: `scripts/rapl-publisher.py` and `scripts/heteroes-rapl.service`.
An administrator can install those reviewed files using:

```bash
sudo install -d -m 755 /usr/local/lib/heteroes
sudo install -o root -g root -m 644 scripts/rapl-publisher.py /usr/local/lib/heteroes/rapl-publisher.py
sudo install -o root -g root -m 644 scripts/heteroes-rapl.service /etc/systemd/system/heteroes-rapl.service
sudo systemctl daemon-reload
sudo systemctl enable --now heteroes-rapl.service
```

The fixed service is installed and active on this host. Other hosts need their
own applicable sensor support; portable installers do not silently gain root.
Windows currently has NVIDIA GPU observations and fixed CIM CPU/RAM readings;
Linux per-thread/I/O/process/hwmon detail and CPU RAPL power are not implemented
through Windows hardware sensors. Native Windows acceptance of this UI remains
pending. An actual reviewed Windows sensor adapter is future work, not an assumed
LibreHardwareMonitor WMI provider.

Samples are cached for three seconds; Worker control polls remain ten seconds.
Server's private CPU Python monitor produces JSON lines every three seconds and
exits on parent stdin EOF. It uses only stdlib collectors, no Torch/CUDA. Server
bundles vendor four reviewed collector modules with SHA256 provenance. Refresh
with `scripts/refresh-monitoring.py --track-a <Track A>` before refreshing source
bundles. Updating those collectors in Track A requires refreshing the vendor copy.

The API retains 180 observations per device and returns 60; desktop recent history
has 60 points. The chart shows actual timestamps and breaks gaps over 30 seconds.
Long-term per-minute resource charts are not implied by day/month energy totals.
The detailed protocol is separately capability-negotiated, preserving rolling
compatibility with older strict Servers. Observation fields never grant device
contribution or prove that a compute process stopped.
