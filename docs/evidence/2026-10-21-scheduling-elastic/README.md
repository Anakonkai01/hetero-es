# Tail-aware scheduling, liveness and elastic membership (predeclared)

Predeclared 2026-10-21 before any code change, branch `feat/r11-scheduling-elastic` from `df2ba0d`.
Design: [ADR-009](../../../runtime/docs/adr/ADR-009-scheduling-and-elastic-membership.md).

## Findings that start this work

| # | Finding |
| --- | --- |
| F1 | B4 `GreedyTail` exists and was measured better, but the managed product allows only greedy |
| F2 | `AdmittedOnly` drops `committed()`, so a wrapped GreedyTail silently behaves like greedy |
| F3 | A new policy per generation means a speed book that forgets; nothing survives a restart |
| F4 | GreedyTail treats a worker busy for more than 30 s as dead (heartbeats not seen) |
| F5 | `capacity-weighted`, `round-robin` and `asynchronous` are advertised with no code |
| F6 | The worker list is frozen when the experiment starts |
| F7 | The stall check counts commits only; a heartbeating long candidate fails the run after 300 s |
| F8 | Generation 1800 s, audit 120 s and other limits are fixed, not derived |
| F9 | Realized versus declared audits are not summarized |
| F10 | Lease expiry is implicit in the ledger |
| F11 | Public `/health` reveals the private lab address |
| F12 | A failed desktop self-test action keeps no exception detail |

Reviewed and kept, with reasons in ADR-009 and the plan:
- the CPU-only noise engine in the product
- no profile admission
- heartbeat wiring
- replay verification every catch-up
- the default chunk
- broad exception handlers

## What will be shown

- New tests first, then the change. Scratch mutation checks for each new rule:
  - hook forwarding
  - shared book
  - heartbeat liveness
  - heartbeat-aware stall
  - membership effect
  - explicit expiry
- **Key invariant:** a CPU end-to-end run in which a worker joins mid-run and another leaves has child hashes equal to a
  fixed-membership run.
- A full `scripts/check-all.sh` pass and a packaging check, then candidate7 packages.

## What this does NOT show

This is not GPU or multi-machine acceptance; that is the separate candidate7 50-generation run. It makes no speed
claim beyond the earlier research measurements, and makes no learning claim. No numerical behavior, recipe identity,
public lab, main branch or release changes here.
