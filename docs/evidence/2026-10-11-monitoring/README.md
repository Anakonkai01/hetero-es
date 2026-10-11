# Monitoring and energy acceptance — 2026-10-11

This is resource/UI acceptance, not a new GPU numerical campaign. Reference-tool
choices, units, identities, persistence, sensor scopes and platform limitations
are in [the design](../../resource-monitoring-design.md).

Verified final source: Track A `9ff2b9c`; Track B HEAD contains this evidence.
Local installers: `monitor-20261011-r2`, [manifest](installers.json) and
[full HTTP download verification](download-checks.json). The intermediate r1
[manifest](installers-r1.json) and the older UI installers remain preserved.
No cloud publish, push, merge, tag, driver change or GPU compute was performed.

- Full CPU runtime: **2,060 passed, 100 skipped**, 73.81 seconds; targeted
  monitoring/Agent: **24 passed**. Covers alias/restart deduplication, hardware
  counter wrap/reset, gaps, midnight splitting, short CPU sensor outages, wall
  meter scope/freshness, process privacy/PID reuse and rolling protocol support.
- Product backend: **99 passed**, including strict bounded detail, real monitor
  JSON lines/parent EOF and vendored SHA256 provenance. Existing Starlette/httpx
  deprecation warning remains; dependencies were not replaced.
- Worker Node: **12 passed**; Server Node: **1 passed**; fleet aggregation:
  **2 passed**. Web lint and all three workspace builds passed.
- [Live page review](web-review.json): **52 layouts** across both themes and
  desktop/mobile; no JS errors/document overflow. Expected anonymous-session 401s
  are retained in the report. Generation/candidate/seed inspection is preserved.
- [Dedicated live monitoring review](monitoring-layout.json): **48 layouts**,
  Vietnamese/English, light/dark, Overview/Detail, Standard/Large and widths
  1440/768/390. No label/value intersections, document overflow or JS errors;
  Detail reports 28 logical CPUs and actual energy components. Live screenshots
  are named `live-monitor-*-viewport.png`.
- [Desktop fixture review](desktop-states-review.json): **26 state/theme cases**,
  testing both views/text sizes at 1100/390 widths, missing/stale readings and
  approval/draining/unknown contribution guards. No metric intersections or
  overflow. Fixtures are renderer tests, not hardware acceptance.
- [Real packaged CPU Server](packaged-linux-server.json): fresh isolated Linux
  runtime, CPU-only dependencies, account bootstrap, held queue, same-origin
  Web/API, real host cores/CPU package watts/persistent energy and Detail rendering,
  close-to-tray, stop, restart-stopped and parent-pipe API exit. Uses Xvfb, not a
  normal owner desktop walkthrough. Profile runtime SHA matches the final bundle.
- Published Linux archives were SHA256-verified, extracted with the safe tar
  filter, and opened in actual Electron under Xvfb in both themes. See
  `packaged-desktop-review.json`. Extracted copies are under Archive-2tb
  `heteroes-local/evidence/monitoring-portable-r2`.
- [Live state](live-state.json): actual i7-14700KF/5070 Ti, 28 logical CPUs,
  20 top processes, 24 hardware sensors; CPU package and GPU watts measured.
  Nested core watts excluded from the subtotal, whole-machine AC unavailable.
  Energy totals survived a real Agent restart. Queue held, zero reservations,
  local contribution OFF, no local GPU compute processes, all 21 original
  experiment bodies/snapshots and all owner contribution flags preserved.

Windows NSIS installers were built and HTTP hashes verified. They have not been
executed natively for this revision. Windows still has basic fixed CIM CPU/RAM
and NVIDIA observations; Linux CPU-power/per-thread/process/hwmon parity is not
claimed. Real GPU Worker installation/qualification and pause/resume acceptance,
normal desktop walkthroughs and cloud acceptance remain separate pending gates.

Private review logs, full screenshots, fresh runtime test data and the pre-cutover
SQLite backup are in `~/.local/share/heteroes-monitoring-review`. Credentials were
not included in committed evidence. Shared electricity ledger is private ext4 at
`~/.local/share/heteroes-power`; monitoring cannot reconstruct unobserved past
energy and does not attribute host consumption to individual jobs.
