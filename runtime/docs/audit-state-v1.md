# Operational audit state and update admission

This is the M2 operational contract added after `2776e88`. It does not change the frozen numerical ledger,
candidate/recipe/update identities, hash sampling or historical three-mismatch quarantine policy.
The current managed recipe has **no strict first-mismatch activation**. That requires M4 backend/recipe identity
and qualification; the strict guard primitive is exercised by internal CPU fixtures only.

## Generation outcomes

`AuditAPI.audit_summary()` returns these generation-local fields:

| Field | Meaning |
| --- | --- |
| `enabled` | Configured coverage is greater than zero. Zero selected at a positive rate is different from disabled. |
| `selected` | Canonically committed text candidates selected by the frozen hash rule. Uncommitted work is outside this denominator. |
| `completed` | Selected candidates with at least one canonical audit row, including mismatches. |
| `matched` | Completed candidates for which every stored audit matches the committed text hash. |
| `mismatched` | Completed candidates with any stored mismatching audit. Neither participant is declared correct. |
| `pending` | Selected candidates lacking audit evidence while the drain is open. |
| `timed_out` | Remaining incomplete candidates when the drain was closed for timeout. |
| `skipped` | Remaining incomplete candidates when closed for insufficient workers or explicit cancellation. |
| `incomplete` | `selected - completed`, regardless of why further work stopped. |
| `drain_reason` | Null while open; otherwise `complete`, `timeout`, `insufficient_workers` or `cancelled`. |

Candidates are counted once, even if several auditors have canonical rows. Therefore
`completed = matched + mismatched` and
`selected = completed + pending + timed_out + skipped`.
The coordinator persists `complete`, `timeout` and `insufficient_workers` at the drain boundary. Explicit cancellation
is supported by `close_drain("cancelled")`; generic run cancellation does not currently add that disposition.

`audit_counts()` remains `(selected, completed)`. `generation_done.audits` carries the detailed summary, including
disabled coverage. The current supervisor/backend/UI still use their earlier aggregate projection; the next product
slice must read canonical outcomes and closure state, rather than assuming that all completed audits matched.

## Drain closure and late delivery

`audit-state/gN.json` stores version, experiment, generation, frozen rate and closure reason. It does not store audit
successes or credentials. Invalid/conflicting existing state is refused. A closed drain admits no new audits on
restart; calling close again cannot replace its original reason. Completed/matched/mismatched counts always come
from current canonical ledger reads, so an accepted late result supersedes an incomplete disposition.

All generation APIs of a coordinator share an audit-only lock and lease registry through `AuditRunGuard`. A result,
heartbeat or restore-failure report posted to the new HTTP endpoint can still authenticate its earlier audit lease.
Candidate scoring and ordinary candidate heartbeats bypass the audit-only lock as before. Descriptor, attempt,
token, audit ID and authenticated worker checks remain in force for old deliveries.

The registry is bounded to 4,096 entries by default (`lease_capacity` is an internal constructor setting). At capacity
only completed entries may be evicted; unfinished deliveries remain available for fault/evidence handling. If every
slot is unfinished, no further audit work is leased and normal drain timeout reports incomplete coverage. Evicted
terminal delivery retries can receive `stale_attempt`; the canonical audit remains in the ledger. Per-generation
lease-request deduplication remains bounded separately. Lease tokens stay in private process memory and are not
recovered after coordinator restart. This is not a persistent lease protocol.

## Run guard and strict evidence primitive

One run-owned guard is shared across API rotation. Audit restore faults remain in `audit-faults.json`; they stop
further work/update admission after restart as well. A failed restore-fault write leaves the process stopped, and a
retry reattempts persistence before returning the terminal quarantine response. This adds no automatic recovery or
device approval change.

The guard serializes fault observation with `record_update`. If a fault wins admission, no further numerical record
is written. If an update was already admitted, it is completed/recovered normally; the next admission is blocked.
No published history is rolled back. The coordinator checks the shared error while waiting and checks again under
the admission lock, closing the race after its last cooperative cancellation check.

Internal `stop_on_mismatch=True` additionally latches the first text mismatch. Before the canonical audit write/ACK
it persists `audit-stop.json` with the descriptor, original worker/attempt/reward/chunk/texts/hash, and auditor
worker/attempt/chunk/texts/hash. Lease tokens and credentials are excluded. The saved receipt is checked against
canonical candidate/completion identity and both text hashes on restart. An existing stop is honored even if a new
caller requests historical policy. Original rewards and the frozen ledger's quarantine threshold are unchanged.
The primitive does not expose a public SDK/API/CLI recipe option.

## Limits and next gates

- CPU fixtures establish protocol, accounting, restart and concurrency behavior; they do not qualify inference on
  GPUs or native Windows, nor prove token identity. The current protocol stores texts and hashes, not token IDs.
- Receipt persistence is tested after successful file fsync/replace and reconstruction of independent guard/API
  objects. No hard-kill or power-loss acceptance was run. A failed storage write keeps the current process stopped;
  immediate process/power loss before a successful retry is not a durable-stop guarantee.
  Directory-fsync/power-loss and real full-disk acceptance remain open. Do not promote strict behavior without
  resolving the required storage-failure contract in M4/M5.
- Retaining a lease lets an in-flight mismatch remain observable; absence of its eventual report is still incomplete
  coverage. This is not proof that all mismatches will be delivered under every failure.
- Cross-process/multiple coordinator writers, persistent audit leases, D10 recovery, stage/progress watchdogs and
  explicit generation hard caps are not implemented by this slice. The one coordinator recovery budget is unchanged.
- Existing recovery-point capture/restore carries `audit-faults.json`, but does not yet carry the new drain/stop
  sidecars. A local process restart is different from restoring onto a replacement installation. M3/M4 must preserve
  these operational dependencies, including faults observed after a point's immutable snapshot; replacement recovery
  is not accepted as preserving the strict stop. This is another strict-promotion gate.
- Product projection/UI and historical unknown-state handling are the next lower-effort work package in
  [the effort split](../../docs/HUMAN-REVIEW-EFFORT-SPLIT.md). M2 and M0–M6 remain incomplete.
