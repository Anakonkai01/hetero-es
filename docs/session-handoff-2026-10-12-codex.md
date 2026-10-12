# Session continuation — 2026-10-12, Codex

Read the original `session-handoff-2026-10-12-lf1.md` for owner rules, decisions,
live deployment and recovery material. This file records the continuation. Owner
authorized unattended local work while away, plus independent backlog work after
the first item. No push/tag, GPU work, second-machine access or persistent system
configuration changes were authorized here.

## First checkpoint: E1 and Worker E2

- Qualified Linux desktop coordinator selection, local LAN/overlay address choice,
  matched enrollment and agent configuration. Windows remains worker-only.
- Paired-device route and role update in one owner-authenticated backend transaction,
  guarded by OFF, confirmed drain and no device/physical reservations.
- Durable pending configuration on uncertain replies; agent stays stopped until
  the owner signs in and confirms a choice. Failed startup retains uncertain bridge
  ownership so a later safe Quit can still confirm drain.
- Read-only desktop connection diagnostics. Lab health, assignment-scoped
  coordinator grant and bounded 64-byte private weights range. Public fallback is
  replay-only; unassigned or unpublished weights is explicitly untested.
- Worker source runtime refreshed; Lab Server archive refresh is part of the final build. No public publication/restart.

Checks: runtime **2114 passed, 100 skipped** (CPU), backend **193 passed**, Worker
Node **25 passed**. Mutation faults detected: Worker **10/10**, backend **6/6**,
runtime **8/8** after closing two test gaps. Real Electron UI checked at 1280, 780,
360 px and for pending-role confirmation; qualification and lab data were synthetic.
Evidence: `docs/evidence/2026-10-12-lf1-codex/README.md`.

## What remains

GPU proof of the new desktop coordinator flow, second-machine/public-network and
native Windows acceptance still need the owner. Lab Server graphical network choice,
CLI doctor route checks and automatic public-compute ingress setup remain unfinished.
The public lab still serves r4, so changing a paired role with the new app will need
the new backend deployed first (`deviceConfiguration` capability in health).

Next independent backlog work: split admission hold from ongoing reconcile; agent
command-capability header. Then build and check installers in isolated CPU profiles.
The identity/epoch, restore and ledger features remain separate, larger tasks.

## Second checkpoint: control continuation

Admission hold now leaves existing-run reconciliation, cancellation, pause and
release projection running. Every queued claim rechecks the hold under the store
lock. Agent polls advertise command kinds in an HTTP header; the body is unchanged.
The server sends only supported commands and retains unsupported pending commands.
Core lifecycle support is needed for admission. Pause and live policy changes on
old agents return 409 before mutating the run. See ADR-005 and ADR-007 updates.
Control mutation checks: 7/7 backend faults and 1/1 agent-header fault detected.

## Third checkpoint: responsive uploads and one production writer

Local uploads keep file opening, chunk writes/hash, fsync/publication and cleanup
in the thread pool. Cancellation serializes cleanup with ongoing disk work.
Production `app_from_environment` locks the actual database path and refuses a
second writer. It releases startup failures, and shutdown joins writer threads off
the event loop before releasing the lock. Mutation checks: storage 6/6, writer 4/4.
No live deployment or schema/numerical change was made.

## r5 preparation and native testing handoff

Build `lf1-20261012-r5` is under
`/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261012-r5/`. Four installers are
prepared and hashed; the prepared receipt is in the evidence folder. Public links
and the live download manifest still point to r4. Both Linux apps passed clean
install checks with isolated system-disk profiles; no GPU work/enrollment. Windows
installers have no Authenticode signature and were never run on Windows here.
See `r5-hardware-acceptance.md` for the next real-machine steps and limits.

The first Server validation profile was accidentally put on Archive, whose
current mount exposes private directories as 0777. Server correctly refused it.
A later system-disk validation passed. Keep SQLite/runtime/private configuration
on the system filesystem. The Worker install took 545 seconds on Archive and 84
on the system profile; no general performance claim is made.

`publish-local-installers.py --prepare-only` creates files/receipt without public
changes. A later publication can use `--prepared-receipt <prepared.json>` and a
new explicit `--receipt`; all reviewed hashes are rechecked before publication,
and no prepared archive is rebuilt. Deploy the backend only through
`scripts/local-lab.py`, after checking the lab is idle; the role-change capability
requires the matching new backend. No push/tag or automatic GPU proof was done.

## Final measured checkpoint

CPU runtime **2115 passed, 100 skipped**; backend **221 passed**; Worker Node
**25 passed**; Server Node **1 passed**. **45/45** listed mutation faults detected
in the final runs. `validation-summary.json` names these counts and
`package-source-check.json` checks packaged hashes and changed source bytes.
Both Linux apps passed clean-install/lifecycle checks in isolated system profiles.
Windows and native desktop/GPU/two-machine acceptance remain unmeasured.
Public r4 health returned 200/ok during validation; public manifest stayed r4.

Working branches remain `feat/local-first-lf1`, no push or tags. Final recovery
material and exact commits are recorded by the session archive receipt under
`~/.local/share/heteroes-session-archives/2026-10-12-codex-r5/` (with an independently
verified encrypted copy on Archive-2tb). Never overwrite the older LF-1 archive.
