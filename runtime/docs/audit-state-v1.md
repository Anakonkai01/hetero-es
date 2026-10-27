# Operational audit state and update admission

This is the M2 operational contract added after `2776e88`. It does not change the frozen numerical ledger,
candidate/recipe/update identities, hash sampling or historical three-mismatch quarantine policy.
Since D9 (2026-10-27) the strict first-mismatch stop is **active for Recipe v3 runs whose evaluation decoder is
`strict_b22_v1`** (ADR-013) and for no other decoder. Every historical decoder keeps the three-mismatch policy.

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
disabled coverage.

## Lab projection (`run_outcomes`)

The lab supervisor adds `auditSummary.outcomes` for Recipe v3 runs, read from the ledger (read-only) and the run's
sidecars; the earlier `completed`, `mismatches`, `selected` and `quarantinedWorkers` fields keep their meaning.
`outcomes` sums the generation fields above over the run (`timedOut` for `timed_out`) and adds `unknown`, `known`,
`rate`, `enabled`, `policy` (`strict-stop`, `historical`, or null without `recipe.json`), `drainReasons` (count of
generations per closure reason, `open` or `unknown`), `strictStop` (candidate, generation and both workers from
`audit-stop.json`) and `restoreFaults`. A missing or conflicting `audit-config.json` or `audit-state/gN.json` makes
`known` false; incomplete candidates of a recorded generation without a valid sidecar, and of an open drain after the
run ended, are `unknown`, never matched. The web page names every outcome and states that zero chosen is not evidence
of checking (`scripts/check-web-audit-outcomes.mjs`, fixture lab).

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
There is no separate option: the coordinator derives the policy from the frozen recipe identity
(`audit_guard.strict_stop_for`). The strict decoder promises the same tokens on every supported GPU, so one text
mismatch is a fault of the system, not a disagreement to outvote. The run ends with `Audit text mismatch requires
operator review`; no further update is admitted and no worker is quarantined or device decision made by this stop.
A restart of the same run honors the saved receipt and stays stopped.

## Limits and next gates

- CPU fixtures establish protocol, accounting, restart and concurrency behavior; they do not qualify inference on
  GPUs or native Windows, nor prove token identity. The current protocol stores texts and hashes, not token IDs.
- Receipt persistence is tested after successful file fsync/replace and reconstruction of independent guard/API
  objects. No hard-kill or power-loss acceptance was run. A failed storage write keeps the current process stopped;
  immediate process/power loss before a successful retry is not a durable-stop guarantee.
  Directory-fsync/power-loss and real full-disk acceptance remain open: the strict stop is enabled (D9), but this
  storage-failure limit stays a stated M5 limit (real full-disk acceptance is DEFERRED by the owner, 2026-10-23).
- Retaining a lease lets an in-flight mismatch remain observable; absence of its eventual report is still incomplete
  coverage. This is not proof that all mismatches will be delivered under every failure.
- Cross-process/multiple coordinator writers, persistent audit leases, D10 recovery, stage/progress watchdogs and
  explicit generation hard caps are not implemented by this slice. The one coordinator recovery budget is unchanged.
- Since M3 (2026-10-27) a v3 recovery point carries `audit-faults.json`, `audit-config.json`, every
  `audit-state/gN.json` and `audit-stop.json` as they were at capture, and restore writes them back. A strict stop
  happens before the next update, so it is normally later than the newest point: restoring that point on a
  replacement installation re-runs the stopped generation without the stop. Faults observed after a point's immutable
  snapshot are not reconciled; replacement recovery is not accepted as preserving the strict stop.
- The lab projection reads files beside the ledger without a lock; a snapshot taken while a drain closes can be one
  poll behind. The page is checked with fixture outcomes, not with a real multi-device run (that is M5).
