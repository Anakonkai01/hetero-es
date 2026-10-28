# M3a evidence (2026-10-10/11)

The browser and Electron checks deliberately do not submit experiments, install
GPU drivers or run qualification. Mock checks are separate from real-server UI.
CPU-only Track A suite: 2041 passed, 100 skipped (CUDA and opt-in conditions).
Backend: 73 passed. Desktop lifecycle/downloader/archive tests: 11 passed.
Native Windows GPU and fresh native Windows installation remain unverified.

An operator mistake invoked the legacy frontend `test:integration` command,
which submitted run `45d72973ddf243fdb8d9a46d2e9a670f` to the unchanged M1 deployment.
It ran one generation on the local 5070 Ti only, then cooperative cancellation
completed. Final state CANCELLED, all owned workers confirmed stopped, zero
reservations, zero queued jobs; NVIDIA compute-process query empty afterward.
No returned 3060 was selected. This is an unintended run, not M3 native evidence.
The default command now performs observation only; actual GPU acceptance requires
both the `--gpu` flag and `HETEROES_GPU_ACCEPTANCE=1`.

Installers and private links are in `installers.json`; native Windows GPU
acceptance remains false. The portable Linux archive avoids a FUSE requirement.
`local-backend-cutover.json` records the held CPU API upgrade with preserved
metadata. No cloud resources were created.

`post-reboot.json` records recovery of the M3 CPU API and web preview after the
11/10 host reboot. Real-server browser acceptance passed again. Dispatch remains
held with zero queue and reservations; no compute agent was started. Track A
source is committed locally as `9ef0d91`.
