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
- Source runtimes refreshed for the desktop apps. No public publication/restart.

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
