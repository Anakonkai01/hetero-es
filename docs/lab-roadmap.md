# Lab product roadmap

Status: accepted by the owner; M1 implemented and verified locally. M2–M6 remain
planned. Recorded on
2026-10-10 from the planning conversation. This file records decisions and
acceptance gates, not claims that future milestones have been implemented.

## Baseline and working rules

- Track A: `../hetero-es-integration`, integration baseline
  `51e1b2a2a5b3ba0206099b3660cc70da4e1f1401`.
- Track B: this repository, integration baseline `7532750`.
- M1 branches: A `feat/lab-operations-control`; B
  `feat/lab-operations-product`. Preserve the previous integration branches.
- Local development and commits are authorized. Do not push, merge, tag, change
  GPU drivers, replace existing Python environments, or publish a public service.
- Keep credentials outside Git. Preserve run IDs, canonical recipes, ledgers,
  checkpoint evidence, and the existing GPU budget. Approximately 0.177 of the
  previously authorized 2 GPU-hours had been consumed at planning time; calculate
  actual usage before starting another GPU campaign.
- English repository documentation; Vietnamese user communication. Real services
  remain the default. MSW must be explicitly selected for demonstrations.
- There is no delivery deadline. Advance only after each milestone's gate passes.

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

Start network deployment with LAN and a stable named Cloudflare Tunnel. A VPS is
an optional later migration, not an initial prerequisite. Public deployment is
outside M1. Domain and tunnel configuration must be settled before M3 publishing.

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

Separate control services from GPU execution. Introduce authenticated worker
identity and outbound management transport. A normal CPU host can operate the
lab, and workers connect without inbound SSH. Retain safe cancellation, replay,
admission and persistent quarantine.

Gate: authenticated worker lifecycle, disconnect/reconnect and stale identity
handling on a server without a GPU; numerical and failure regressions pass.

## M3 — Installable Windows/Linux product and networking

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
