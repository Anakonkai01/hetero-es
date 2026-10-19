# Lab operations extension (M1)

The accepted product roadmap lives in the sibling Track B repository:
`Hetero-ES-LLM/docs/lab-roadmap.md`. Its implementation record is
`Hetero-ES-LLM/docs/m1-implementation.md`. The owner authorized M1 implementation
on 2026-10-10; later M2–M6 milestones remain planned.

Track A's M1 scope is idle maintenance and runtime-owned snapshots. The product
continues to own identity, membership, resource assignment and its FIFO. Track A
continues to own all ledgers and numerical state. There is one global active run.

Authenticated loopback control endpoints:

- `GET /maintenance`: current durable hold or null.
- `POST /maintenance/acquire`: return a hold ID only after all runs are terminal,
  coordinators are dead and all started workers have confirmed shutdown.
- `POST /maintenance/release` with `maintenanceId`: release the matching hold.
- `POST /backups` with `maintenanceId`: create a runtime-owned idle tar snapshot.
- `GET /backups/{backupId}`: stream that snapshot to the product backup service.
- `DELETE /backups/{backupId}`: retire a completed transfer archive after the
  product verifies its complete combined backup; original run evidence remains.

The durable hold survives service restart and rejects submissions. Snapshot
creation holds the same supervisor lock as submission and ticking. Ledgers are
copied using SQLite's backup API. Every retained regular file has a size and
SHA-256 manifest entry. Symlinks and unexpected state roots are rejected. Process
identity records and live control flags are excluded, as are SQLite sidecars;
historical state, events, ledger and canonical weights are retained. Persistent
quarantine is included. No worker is launched or signalled by snapshot creation.

Transfer snapshots stay outside Git under the configured runtime state parent's
`runtime-backups/` directory with private permissions. The product combines them
with a consistent product database copy and retires the intermediate transfer
after verifying the combined archive. A failed cleanup is recorded for operator
review; a successful combined backup remains valid. Original run evidence is
never deleted by retirement.
Product restoration requires a new deployment directory, new process/worker
paths and runtime credentials, revoked sessions, and an explicitly held queue.

CPU verification: 2,143 passed, 21 skipped in the full suite. New maintenance and
backup contracts include restart persistence, unknown shutdown rejection, exact
archive contents and refusal of symlink input. A scratch mutation disabling the
submission maintenance guard was caught. Real product browser, two-GPU execution,
33.6 GB backup/restore and restored cold-boot acceptance also passed. Sanitized
evidence is in `artifacts/experiments/2026-10-10-m1-lab-operations/`; the full M1
implementation record is maintained by B. M2–M6 remain planned.
