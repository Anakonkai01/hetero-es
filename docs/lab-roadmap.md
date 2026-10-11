# Lab product roadmap

**2026-10-11 execution revision:** the owner authorized implementation through M6
locally, removed GPU-hour and total-run budget caps, and selected Archive-2tb for
large data and independent encrypted archives. Technical timeouts and GPU opt-in
remain. Historical limits below are superseded. See
[current implementation progress](local-lab-progress.md) for decisions and gates.

Status: accepted by the owner; M1 implemented and verified locally. M2 local
agent/control/recovery is verified; cloud acceptance is deferred. M3a native
Worker/shared UX is implemented, with the first Windows RTX 3060 hardware trial
passed; packaged Linux GPU and remaining lifecycle/outage gates are pending.
M3b–M6 remain planned. Decisions revised on 2026-10-10; progress updated
2026-10-11. Resume from the [session handoff](m3-session-handoff.md).
This file records decisions and
acceptance gates, not claims that future milestones have been implemented.

## Baseline and working rules

- Track A: `../hetero-es-integration`, integration baseline
  `51e1b2a2a5b3ba0206099b3660cc70da4e1f1401`.
- Track B: this repository, integration baseline `7532750`.
- M1 branches: A `feat/lab-operations-control`; B
  `feat/lab-operations-product`. Preserve the previous integration branches.
- Local development, isolated device deployments and M2 cloud deployment within
  the agreed free-tier limits are authorized. Do not push, merge, tag, change
  GPU drivers or replace existing Python environments.
- Keep credentials outside Git. Preserve run IDs, canonical recipes, ledgers,
  checkpoint evidence, and the existing GPU budget. Approximately 0.177 of the
  previously authorized 2 GPU-hours had been consumed at planning time; calculate
  actual usage before starting another GPU campaign.
- English repository documentation; Vietnamese user communication. Real services
  remain the default. MSW must be explicitly selected for demonstrations.
- There is no delivery deadline. Acceptance gates remain required. The owner authorized independent M3a local
  development while M2 cloud acceptance is deferred.

## Product and deployment decisions

The product consists of a Lab Server and a Worker application. The server owns
identity, workspaces, scheduling, run records and artifacts. It must eventually
run without a GPU. Track A retains numerical execution and canonical state;
Track B owns the user interface and product operations.

Support both a self-contained local lab at a school/cafe and workers contributing
to an existing remote lab. Windows and Linux are required for both server and
worker packaging. The eventual worker application uses Electron/React and an
isolated Python runtime. Nontechnical owners should install, sign in and run a
self-test without SSH, Tailscale or WSL commands.

M2 adds a CPU-only AWS control server, R2 storage and a fixed free HTTPS address
(DuckDNS unless the owner supplies another address). Keep Tailscale for compute
traffic initially. A Cloudflare compute tunnel and desktop installers are later
work; the owner's cloud proposal is background, not a requirement to reproduce.

Contribution defaults to OFF, requires explicit activation and does not resume
automatically after restarting the app. Closing its window keeps the tray
process running. Turning contribution off drains work safely. A GPU belongs to
at most one contributing workspace at a time.

Multiple independent workspaces are required. Anyone can register, but a
platform administrator approves accounts before resource access. Only accounts
granted `canCreateWorkspace` may create workspaces. Experiment owners see their
own experiments; workspace administrators see all experiments in that workspace.
Platform administration does not automatically grant access to workspace data.

Parallel execution initially uses disjoint GPU sets. Sharing one GPU across
simultaneous jobs is later research. Current full-model workers do not pool VRAM.
Native Windows execution and additional models must pass compatibility gates;
never weaken numerical contracts to make them pass.

## M1 — Lab operations (current implementation scope)

Deliver registration and account approval, workspace creation and membership,
resource assignment, operational visibility and safe backup/restore. Keep the
current static host configuration, manual service startup and one global active
experiment. Do not begin worker installers or parallel scheduling in this step.

Requirements:

1. Versioned SQLite migration preserving existing users, `lab` membership, run
   UUIDs, queue order, experiment data and checkpoint references. Test against a
   copy of the live database before migration.
2. Account states `PENDING`, `ACTIVE`, `REJECTED`, `SUSPENDED`. Pending users may
   view their status and profile only. Separate platform administration from
   workspace roles; remove authorization based on the literal username `admin`.
3. Platform approval/rejection/suspension and workspace-creation permission.
   Editable profile, password changes and session revocation. Audit privileged
   actions; account or membership revocation blocks new jobs, cancels queued work
   and requests cooperative cancellation of active work while retaining evidence.
4. Workspace creator becomes administrator. In-app invitations use usernames,
   with acceptance, membership roles and removal. Never remove or demote the last
   workspace administrator. Do not send email in M1.
5. Enforce membership, workspace and owner/admin visibility on experiments and
   every child route, including direct IDs, events, models, datasets and downloads.
6. Assign each configured GPU to at most one workspace, backfilling the current
   pool into `lab`. Reassignment requires confirmed idle runtime ownership; unknown
   processes or draining work block reassignment. Revalidate frozen queued worker
   selections before launch. Expose queue position and waiting reasons without
   revealing another workspace's private experiments.
7. Operations page for service health, launch failures, offline GPUs, unknown
   shutdown reservations and persistent quarantine. Quarantine is never silently
   reset; do not substitute GPUs that the owner did not select.
8. Idle-only backup and restore. Block dispatch and new submissions during the
   operation, including recovery, cancellation, draining and unknown ownership.
   Product SQLite is backed up consistently; runtime snapshots are supplied by A,
   not obtained by B reading or changing A's ledger directly. Include a versioned
   manifest and checksums; reject incomplete/corrupt bundles and unsafe paths.
9. Restore into a new deployment directory, never overwrite an existing one.
   Revoke imported sessions and hold the imported queue until an administrator
   explicitly confirms worker configuration/startup. Preserve historical IDs and
   evidence. Never reuse old process identity records or signal unrelated PIDs.

Acceptance gate:

- Account approval, workspace permission, invitations and last-admin protection.
- Cross-workspace and owner isolation on all child routes and downloads;
  revocation is effective for sessions and queued/active work.
- Migration preserves baseline counts, IDs, queue order and checkpoint hashes.
- Idle backup/restore round trip and corrupt/unsafe bundle rejection; restored
  queue stays held and no historical process is relaunched accidentally.
- Browser registration → approval → workspace membership → create/submit/cancel
  → real result/artifact access. Existing two-GPU flow remains valid.
- Relevant backend/runtime tests, frontend build/lint and explicit mock checks.
  CPU checks first; any real GPU validation stays within the original budget.

## M2 — GPU-independent control and worker identity

Accepted revision, 2026-10-10: website remains available and accepts queued jobs
when GPUs are off. Cloud and local use the same product. Keep SQLite and one
backend process, with one global active experiment until M4. Preserve accounts,
workspace isolation, numerical recipes, ledger ownership and M1 history.

Implementation branches: A `feat/m2-agent-runtime` from `a084418`; B
`feat/m2-cloud-control` from `a3e39db`.

1. CPU server owns users/workspaces, device registry, durable assignments,
   queue, cached monitoring and artifact permissions. It never loads CUDA,
   canonical weights or a live candidate ledger.
2. CLI GPU agents connect outbound over HTTPS. Pairing codes expire after ten
   minutes and are single-use. Devices have UUIDs, owner identity, revocable
   credentials, self-test evidence and separate administrator approval.
   Preserve legacy worker aliases; add Thao's 3060 under a distinct alias.
3. Contribution resets OFF on each agent boot. Explicit owner activation is
   bound to that boot. Adopt owned surviving processes without relaunching;
   recovering a dead coordinator requires activation. Commands are typed and
   idempotent; never accept arbitrary shell commands or paths from the browser.
4. Select a coordinator explicitly from approved capable devices. Reserve the
   coordinator and every selected worker atomically. A heartbeat timeout only
   changes connectivity; it never releases ownership or launches a replacement.
   Release requires confirmed process shutdown on every selected device.
   Assignment/epoch checks fence stale reports and commands. Do not automatically
   fail over while a previous coordinator may still compute.
5. Compute credentials bind each authenticated device to its worker alias and
   assignment. Existing computation continues through control-server outages;
   durable local events are replayed with deduplication when connectivity returns.
   Queued jobs wait for selected devices; no silent device substitution.
6. Recovery points include consistent SQLite backups, required immutable
   weights, configuration, recipe/revisions and checksums, captured at completed
   generation barriers. Defaults: interval K=1 and retain N=3; configurable.
   Always retain a final point. Operational backup policy does not change Recipe
   v1 numerical identity. Upload asynchronously and publish a manifest last.
7. Use private Cloudflare R2 through a minimal S3-compatible backend. Master
   storage keys stay on the CPU server; agents get limited upload URLs. Verify
   content, size and manifest before READY; ETags are not SHA-256. Downloads
   require workspace authorization. No public bucket or secret-bearing logs.
8. Stay within free storage: 8 GB project quota including reserved uploads and
   multipart data, warnings plus hard upload rejection. Check account-wide usage
   and request limits. Quota/network errors leave computation running and keep
   consistent local points with visible pending/error sync state. Retention must
   preserve referenced objects and previous valid points until a new point is
   verified. Product database backups: hourly, up to 24 within quota.
9. Import M1 metadata and one selected sample checkpoint; keep the complete
   33.6 GB M1 backup locally. Restore to a fresh directory, verify hashes, hold
   dispatch and retain lineage. No imported PID reuse or automatic reassignment.
10. AWS: verify actual Free Plan, credits, expiry and instance eligibility before
    provisioning. Prefer eligible x86 `t3.small`, Singapore; use `t3.micro` if
    necessary. Do not upgrade to Paid Plan. CPU credits use standard mode.
    Single API/static website with automatic HTTPS; no NAT gateway, ALB or RDS.
    Keep API internals private. Cloud admin password is separate and at least
    12 characters; local admin stays as configured by the owner.

Sequence: M2a local CPU control/agents and fault tests; M2b verified storage and
restore; M2c real AWS deployment and idle cutover. Prepare code and deployment
configuration before asking for missing cloud authentication. Hold the legacy
dispatcher before any agent GPU campaign or cutover. Rollback retains the latest
M2 database with dispatch held, rather than downgrading new history to M1.

Gate: CPU/device/auth/outage/stale-command tests; relevant runtime/backend and
frontend checks; real R2 upload/download/restore; actual cloud browser access;
5070 Ti plus Quang's and Thao's 3060 each commit candidates. Use at most another
0.5 GPU-hours within the original 2-hour budget, recalculated before execution.
M2 remains incomplete without the cloud and three-device evidence. Record progress
and blockers in [m2-implementation.md](m2-implementation.md).

## M3a — Native Worker and shared product UX

Owner accepted 2026-10-10: worker-first Windows 11 x64 native and Linux x64
installers, existing local CPU server, Tailscale graphical setup, shared Vi/En UI,
light/dark/system and three accents. No Lab Server installer or cloud prerequisite
for this slice. Native numerical admission and fresh hardware usability remain
required before claiming acceptance. See [M3a implementation](m3-local-worker-ux.md)
and [worker trial guide](worker-desktop-guide.md).

## M3b — Installable Lab Server and public networking

Package server and worker applications with isolated dependencies, login,
contribution controls, tray behavior and compatibility self-test. Support local
lab startup and remote contribution via LAN/stable named Cloudflare Tunnel.

Gate: a nontechnical person installs on fresh Windows and Linux machines,
starts a CPU lab or contributes a GPU, and diagnoses failed self-tests without
terminal setup. Native Windows must pass numerical compatibility before admission.

## M4 — Parallel jobs on disjoint resources

Add atomic GPU ownership leases. Run jobs concurrently only on disjoint GPU sets.
Use FIFO among eligible jobs so a blocked job does not stall unrelated resources.
Pause/resume at generation boundaries, releasing resources while preserving the
same run ID, immutable configuration, ledger and checkpoint lineage.

Gate: no double allocation under concurrent submission, cancellation, crash or
recovery; independent jobs progress and generation-boundary resume is exact.

## M5 — Text models, datasets, evaluation and export

Add a model registry with pinned Hugging Face revisions/safetensors and local
bundles. Qualify Qwen, SmolLM and TinyLlama sizes against real VRAM and compatibility
gates. Add JSON/JSONL/CSV text data with explicit field mapping and immutable
dataset, prompt and evaluator versions. Show training reward, validation each
generation and final test predictions/metrics. Export a usable model bundle with
tokenizer, configuration and checksums. Version Recipe v2 without changing v1 hash
semantics or claiming VRAM pooling.

Gate: reproducible data splits and model identity, held-out reporting, successful
export/reload, and cross-worker numerical regression for each admitted combination.

## M6 — Reliability and handoff

Run load/fault campaigns, fresh-site installations, upgrade/rollback and operator
handoff. Label simulation evidence separately from real hardware evidence.

Gate: documented failure recovery, installation and upgrade evidence, resource
isolation under load and an operator able to run the lab from the shipped guide.

## Implementation record

Record M1 progress and verification in [m1-implementation.md](m1-implementation.md).
Future milestones above remain planned until their evidence gates are met.
