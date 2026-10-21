# ADR-009 — Tail-aware scheduling, liveness and elastic worker membership in the product

Status: **ACCEPTED** by the owner on 2026-10-21 (chat answers, see the end). Related: ADR-002 (ledger, leases),
ADR-005 (lifecycle authority), ADR-008 (Recipe v3; this ADR changes nothing in its documents or hashes).

Labels: **[CODE]** exists in the tree · **[DECIDED]** owner decision of 2026-10-21.

## Context

The research runtime measured four dispatch policies (`heteroes/dispatch.py`). The tail-aware policy B4 `GreedyTail`
was the only one whose gain over the best single machine excluded "no effect" (STATUS C2; G6 FP16 0.94× with greedy
against 1.06× with tail-aware, G7 CUDA 0.95× against 1.09×). The managed product run, written later (commit `51e1b2a`),
hard-codes `AdmittedOnly(Greedy(), workerIds)` and every layer above it (supervisor, backend capability and
validation, web form) accepts only `greedy` + `synchronous`. No document records a reason; it was an omission.

An audit on 2026-10-21 found further gaps around it:
- `AdmittedOnly` drops the `committed()` hook, so `AdmittedOnly(GreedyTail)` would never learn speeds.
- A new policy object is created each generation.
- A worker busy for more than 30 s looks dead to GreedyTail.
- The stall detector counts only commits, not heartbeats.
- The time limits are fixed numbers.
- The experiment's worker list is frozen at submission.
- Three option names (`capacity-weighted`, `round-robin`, `asynchronous`) are advertised with no code behind them.

## Decision

1. **Policies.** The product offers `greedy-tail` (B4, default for new experiments) and `greedy` (B3). The other names
   are removed from the templates, types and labels. Asynchronous ES stays FUTURE (a separate ADR after r11). [DECIDED]
2. **Policy state.** One `SpeedBook` per run, shared by every generation's policy. After a coordinator restart it is
   seeded from the ledger's committed attempt durations. `AdmittedOnly` forwards every optional hook. A heartbeat
   counts as "alive" for the policy.
3. **Liveness.** The stall check fails a generation only when nothing was committed AND no leased candidate sent a
   heartbeat for the stall period. The generation and audit time caps are derived from the measured speeds, never below
   the previous fixed values. [DECIDED]
4. **Elastic membership.** Workers can join or leave a running experiment, either when the owner adds or removes them,
   or automatically when the experiment opts in with `allowJoin`. [DECIDED]
   - A change takes effect at the next generation boundary.
   - Every change is written to the ledger (the `membership` table, see 6).
   - A leaving worker gets no new lease; its current lease finishes or expires and is retried elsewhere.
   - The last worker cannot be removed.
5. **Explicit expiry.** When another attempt takes over a lease that ran out, the ledger writes it to an `expiry`
   table, so the ledger itself shows a timed-out attempt.
6. **No schema break.** `membership` and `expiry` are additive tables created on open, like the existing
   `generation_context`, so the version stays 6. This changes the plan, which said schema 7. A candidate6 ledger,
   including the preserved attempt2 evidence, still opens; an older runtime ignores the new tables. The unused
   `RUNNING` candidate state stays in the `CHECK` constraint, because removing it would rebuild the table.
   `failure_kind` keeps its meaning: an expiry is not a failure the worker reported, so dispatch is unchanged.
7. **Contribution OFF.** Turning a worker OFF used to cancel every experiment that reserved it. Now a worker that is
   not the coordinator and not the last member leaves at the next boundary instead. The coordinator or the last
   member still cancels, as before.
8. **A member that comes back is started again** (owner: "sửa luôn", 2026-10-21, after the candidate7 acceptance
   showed it). Before, the supervisor started a worker only at preparation or on a first JOIN, so a member whose
   process died (machine off, app killed, crash, two minutes without the coordinator), was away at preparation, or
   left and was added back stayed idle until the end of the run.
   - While the run is RUNNING, a member whose worker is confirmed stopped is probed; when its device answers and is ON
     it is started again. A device that is away or OFF is asked again every 30 s.
   - A restart is a new **launch** with its own number (0 is the first, absent on the wire for older labs and
     agents). The lab queues it as its own command and reads only that launch's process report; the device runs it in
     its own directory `r<recovery>-l<launch>` and refuses while an earlier launch may still be running.
   - Never for a quarantined worker, never while the old process's state is unknown, and at most 20 launches per
     worker and coordinator recovery.

## Why the numbers cannot change

The policy and the membership decide only *which worker* evaluates *which candidate*. The recipe hash is built from
`model`, `weightSpace`, `sigma`, `population`, `generations`, `batchSize`, `evalChunk`, decoder, sampler, prompt and
scorer fields (`heteroes/v3/run.py`). It never reads `schedulerPolicy`, `workerIds` or membership.
- Candidate seeds and signs are fixed by the plan.
- The update uses the rewards in index order, whoever computed them.
- The nine-case probes show that the 5070 Ti, both 3060s and the 1660 SUPER give the same token arrays.

A CPU end-to-end test must show that the child hashes of a run with a mid-run join/leave equal those of a
fixed-membership run.

## Owner answers (2026-10-21)

- Fix before the 50-generation acceptance; the acceptance runs on candidate7.
- Elastic now, both manual and opt-in automatic joining.
- Limits derived automatically, heartbeat-aware.
- Remove the dead names; keep greedy and greedy-tail; greedy-tail is the default.
- The acceptance adds a machine around generation 10 and removes it around generation 30.
- Separate finding: the public health endpoint stops returning `privateLabUrl`; it moves behind sign-in.
