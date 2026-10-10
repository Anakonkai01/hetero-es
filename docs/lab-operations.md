# M1 lab operator guide

Accepted roadmap: [lab-roadmap.md](lab-roadmap.md). Current validation and local
branches: [m1-implementation.md](m1-implementation.md).

## Accounts and workspaces

The original accounts and `lab` membership are migrated in place with existing
experiment IDs, snapshots and queue order preserved. Their passwords stay the
same. The initial administrator is granted persisted platform administration
and workspace-creation permission. Authorization thereafter uses these stored
privileges, not the account name.

New users choose **Register an account** on the sign-in screen. Registration
requires a unique username and a password of at least 12 characters. Pending,
rejected and suspended accounts can view their status and edit their profile;
resource access requires an active account.

A platform administrator opens **Operations** to approve/reject/suspend
accounts, grant workspace creation, change platform privileges or revoke
sessions. The last active platform administrator cannot be removed. Suspending
an account revokes existing sessions, cancels its queued jobs, requests safe
cancellation of active jobs and disables owned GPU contributions. Reactivating
the account does not silently reactivate those contributions.

An account with workspace-creation permission chooses **Create workspace**.
Its creator becomes a workspace administrator. Administrators invite approved
accounts by username on the workspace page. Recipients accept on **Profile**.
Roles and removals are managed on the workspace page; the last active workspace
administrator cannot be demoted or removed. Removing membership cancels queued
jobs, drains active jobs and disables contributions owned in that workspace.
Profiles and password changes are under **Profile**. Password changes preserve
the current session and revoke other sessions.

Workspace members see their own experiments and child objects. Workspace
administrators see all experiments in that workspace. A platform administrator
must also have membership and the appropriate workspace role to read an
experiment. Switching workspace discards cached data; membership/role changes
are refreshed and also discard cached scoped data.

## Configured GPUs and queue

M1 retains administrator-configured hosts and existing manual startup. It does
not install a native worker app or introduce dynamic host registration.

The legacy GPU pool is assigned to `lab`; its initial owner is the migrated
administrator. **Workers → GPU contribution** lets owners select one contributing
workspace. Platform administrators can assign a configured GPU's owner to an
active account. The owner must belong to the selected workspace. Enable/move or
ownership transfer acquires an idle runtime maintenance hold before committing
the assignment. Unknown shutdown, recovery, draining or active ownership blocks
the move. This operation temporarily holds the global dispatcher.

**Turn off and drain** disables new use immediately, cancels queued jobs selecting
that GPU and safely cancels active jobs. The prior workspace assignment is kept
for traceability during draining; enabling it elsewhere requires confirmed idle
shutdown. Idle and enabled inventory is workspace-scoped. Frozen worker choices
are revalidated before dispatch, so a queued job cannot take a GPU moved into a
different group. The existing runtime quarantine stays persistent.

There is still one global active experiment and persistent FIFO. **Experiments →
Queue** shows the positions/reasons of visible jobs without showing another
workspace's experiment content. Worker substitution, pause/resume, arbitrary
models/data and parallel jobs remain later milestones.

## Backup and restore

**Operations → Create idle backup** requires no active, recovering, cancelling,
draining or unknown runtime ownership. The product durably holds dispatch and
new submissions, then acquires a runtime hold. Track A supplies an idle snapshot
using its own SQLite backup API; the product never opens a live runtime ledger.
The result combines `product.sqlite` and `runtime.tar` with a versioned checksum
manifest. Historical ledgers, retained canonical weights, events and quarantine
are included. Live PID records and process flags are excluded. Backup files stay
outside Git, under the product state's `backups/` directory.
The temporary runtime transfer is retired after the complete combined backup
has been verified. Failed transfer cleanup is recorded in platform activity;
the verified combined archive and original run evidence are retained.

Backup download is an explicitly privileged, audited operation and contains the
whole lab's private persisted data, including password hashes. Store it as a
private operator artifact. Normal workspace experiment access remains scoped.
The browser obtains a short-lived, one-use HttpOnly download authorization tied
to its live administrator session and streams the file using a native download;
it does not load the complete backup into JavaScript memory. Revoking the session
also invalidates that download authorization.
Large backups contain all retained weights and may take several minutes.
If acquisition or verification fails, the deployment stays held for review;
**Resume reviewed deployment** requires explicit worker-configuration confirmation.

Restore with the backend interpreter, into a directory that does not exist:

```bash
.venv-backend/bin/python scripts/restore-lab.py \
  /private/backups/heteroes-lab-BACKUP_ID.tar \
  /private/deployments/restored-lab \
  --source-config "$HOME/.config/heteroes-integration/config.json"
```

The restore rejects unsafe paths, links, duplicates, incomplete manifests,
checksum mismatches, incompatible product schemas and active runtime history.
It verifies contents in a private staging directory. Imported sessions are
revoked and the queue stays held. Accounts/password hashes, run IDs, queue order,
snapshots and canonical checkpoint bytes remain. Existing deployments are never
overwritten or stopped by restore.
Restore checks available space before staging. Allow room for both the nested
runtime transfer and extracted weights, in addition to the retained source bundle.

`--source-config` reuses existing host/interpreter settings while binding new
product, runtime and process directories, separate worker-state directories and
a newly generated private runtime token. Review `restored-lab/private/config.json`
before starting. Without this option, bind those private settings manually using
`restore.json` as the checklist. Use original account passwords to sign in;
restore does not reset them or write them into the new config.

Only one deployment may own the configured ports. Stop the old deployment
normally before starting the restored one. For validation while the restored
queue stays held, configure distinct `controlPort`, `backendPort`, `uiPort` and
`workerPort`/`workerUrl`; defaults preserve the original ports. Before resuming
dispatch, stop the old controller if it manages any of the same physical GPUs.

```bash
HETEROES_PRIVATE_CONFIG=/private/deployments/restored-lab/private \
  ./start-integration.sh
```

Sign in as a platform administrator, open **Operations**, review worker settings
and explicitly resume dispatch. Imported history is terminal and no historical
process is relaunched. Original deployment data and credentials are preserved.

## Verification

```bash
.venv-backend/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run lint
cd frontend
VITE_DATA_SOURCE=mock node scripts/check-local-demo.mjs
node scripts/check-lab-operations.mjs --run-gpu
```

The last command uses the real product, creates a dedicated acceptance account
and workspace, temporarily moves the idle 3060, executes/cancels a short GPU run,
suspends that account and returns the idle GPU to `lab`. It retains audit/history
and writes browser evidence outside Git. Omit `--run-gpu` for product-only checks.
This command is separate from the explicitly simulated MSW behavior checks.

For a full-size idle snapshot/restore check (requires space for the runtime
snapshot, combined bundle and inactive restored directory):

```bash
.venv-backend/bin/python scripts/check-lab-backup.py
```

This verifies all archive checksums, preserved experiment/workspace/queue rows,
checkpoint references, revoked sessions, new private runtime token and separate
process/worker paths. It leaves the restored directory inactive and held.
