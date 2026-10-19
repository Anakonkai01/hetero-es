# ADR-007 — Identities, compatibility and complete recovery

Status: **PROPOSED**, with the owner decision D5 (2026-10-12) recorded as DECIDED.
Related: ADR-004, ADR-005, ADR-006.

Evidence labels: **[CODE]** exists in the inspected tree · **[MEASURED]** a dated
run in evidence · **[PROPOSED]** recommendation · **[PENDING]** not yet accepted
by a test or run.

## Decision

### 1. Identities

| What | Identifier | Rule |
|---|---|---|
| Lab | `labId` (today called `serverInstanceId`) | Stored **in the management database**, created at initialization. Never derived from a domain, URL or IP. |
| Control authority | `authorityEpoch` (integer) | Stored in the database. **DECIDED (D5).** See 2. |
| User, workspace | user id, workspace id | unchanged |
| Device, worker alias, physical GPU | device UUID, alias, `GPU-…` UUID | unchanged; an alias is a label, the GPU UUID identifies the card |
| Agent run | boot id | a new boot always starts OFF [CODE] |
| Work | experiment id, assignment id + epoch, recipe hash, candidate/attempt id, canonical weights hash | unchanged |

Changing an endpoint changes no identity. Compute grants are bound to one
assignment and epoch; a forged `worker_id` in a payload cannot take another
worker's leases. [CODE] `worker_api.py:160-173`, `devices.py:418`

**Today the lab id lives only in `config.json`** (`server.py:48`). A database backup
loses it; copying the whole config duplicates it, so "moved" and "copied" look the
same. [CODE] The restore script writes a minimal config without it. This ADR fixes
that by moving the id into the database.

### 2. Relocation and fork — DECIDED (D5)

- **Relocation** (the lab moves to another machine): same `labId`, `authorityEpoch`
  + 1. The old server must be off. Every agent remembers the highest
  `(labId, epoch)` it has seen and obeys only that; a lower epoch or another
  `labId` is refused.
- **Fork** (a second, independent lab): new `labId`; every device must enroll again;
  old device tokens are not valid.
- The operator chooses at restore time (`--relocate` or `--fork`). Both start with the
  admission hold on and the imported reservations kept (ADR-005).
- Today only the Electron Worker app compares the id, and only when its URL changes
  (`service.cjs:39-41`); the Python agent never checks it. [CODE] Note: `labId` is
  public and is a consistency check against operator mistakes, not authentication of
  the server. Protection against an impostor is the encrypted overlay or TLS
  (ADR-006).

### 3. Trust

Per-device credentials do not prove that a reward is honest. This stays a
trusted-lab system; no claims about untrusted volunteer compute.

### 4. Compatibility — separate checks, not one version string

| Dimension | Rule |
|---|---|
| Control API and agent protocol | The server advertises capabilities; the agent states its command kinds in an HTTP **header** (the `Poll` body rejects unknown fields, so a new body field breaks an older server); the server sends only understood commands; an agent isolates a bad command instead of stopping (ticket 1.2). [CODE] `agent.py:389-391` is the gap |
| Management schema | One versioned `migrate()` that also covers the agent and study tables. Today `SCHEMA_VERSION = 1` covers the base tables only; agent tables and the `assignments` rebuild run at every start without a version change (`devices.py:267-297`). A newer database refuses an older binary [CODE for the base]. Ticket 3.5 |
| Runtime and model profile | Pinned files; qualification per device; the self-test carries `recipeVersions` and `qualifiedModelHashes` [CODE]. Windows is qualified as Recipe v1 **worker only** [CODE `devices.py` SelfTest validator] |
| Recipe, noise, update, replay formats | v1 serialization and golden hashes do not change; unknown versions are rejected |
| Training ledger | Runtime-owned. Recipe v2 adds a `generation_context` table when a ledger is opened, with the schema number still 5 (`ledger.py:419`). [PROPOSED] record features in a small table and keep the integer, so v1 tools still read v1 ledgers. Touches `ledger/`: needs its own numerical-owner review |
| Backup and export manifest | Explicit version, full file inventory, byte hashes, lineage check before restore |

### 5. Complete recovery (agent mode)

Today agent mode has an hourly management-database snapshot (`cloud_metadata.py`) and
a recovery point per generation, but **no single bundle** that closes the loop: the
whole-lab backup route returns 409 in agent mode (`lab.py:367-368`) and the metadata
restore writes a fresh minimal config. [CODE] [PROPOSED] the lab export must list and
verify:

1. a consistent management-database snapshot, including `labId`, epoch, queue,
   permissions, reservations and epochs;
2. the lab configuration (addresses, storage settings) and the storage signing key,
   through a protected backup with an explicit secret policy;
3. runtime ledger snapshots taken at a generation barrier, with the canonical
   weights they reference;
4. every model, tokenizer and dataset file referenced by hash, **present in the
   bundle**: a hash or an expired URL is not a restore payload;
5. selected checkpoints and export manifests, when used.

Restore rules: into a fresh directory; verify every hash; start HELD; re-resolve local
paths; discard process records (never reuse a PID as an instruction); browser sessions
revoked; require the current owner's ON; new epochs and grants on resume; the previous
controller must be unable to dispatch (epoch, section 2). There is no transaction
across the database, the ledger and the object store, so use generation barriers,
immutable publication and a final manifest naming the chosen lineage; never combine
arbitrary "latest" files. For acceptance, one copy must live outside the coordinator's
disk. Tickets 3.4, 2.4.

### 6. Rollback

Roll back to a verified compatible release plus the newest retained history, in an
isolated held deployment. Never downgrade a schema blindly and never overwrite newer
evidence with an older database.

### 7. Smaller items

- Device-token rotation in the MVP means enrolling the device again (a revoked device
  needs a new alias, `devices.py` approve). Automatic rotation is deferred.
- Reservations protect a GPU only inside one lab database. If two labs may ever share
  a machine, add a per-GPU advisory file lock taken by any coordinator or worker
  process. [PROPOSED, optional, not before multi-lab]

## Acceptance

Restore a lab export onto a fresh path with `--relocate`: the old server, if started
by mistake, cannot command any agent. Restore with `--fork`: devices must re-enroll.
A newer database refuses an older binary. v1 golden hashes unchanged. [PENDING —
tickets 3.3–3.5]

## Still open

Exact manifest fields of the lab export; secret retention policy for disaster
recovery.

## 2026-10-12 continuation — agent command capabilities

[CODE] Each device poll sends `X-HeteroES-Agent-Commands`; the strict JSON Poll
body is unchanged. The server intersects the declared kinds with its own known
set before returning commands. Unknown/future commands stay pending and cannot
block delivery of understood cancel/stop commands. No header means the
conservative core floor (contribution, coordinate, worker start/stop, cancel);
an explicitly empty header understands none. Malformed/oversized headers are
rejected before updating the boot or accepting reports.

[CODE] The last advertised capabilities live in the existing management settings
table, under a device-scoped key. New admission needs all core lifecycle commands.
Pause and live backup-policy changes require the corresponding capability and
return 409 without changing the run when it is absent. Headerless old agents must
upgrade to use those optional features. An old server ignores the new header.

[MEASURED — CPU tests] Agent header test and backend protocol/admission tests, with
mutation checks, are in product `docs/evidence/2026-10-12-lf1-codex/`.
