# ADR-005 — Who owns what: management, numbers and processes

Status: **PROPOSED**, with the owner decision D4 (2026-10-12) recorded as DECIDED.
Related: ADR-002, ADR-004, ADR-006, ADR-007.

Evidence labels: **[CODE]** exists in the inspected tree · **[MEASURED]** a dated
run in evidence · **[PROPOSED]** recommendation · **[PENDING]** not yet accepted
by a test or run.

## Decision

1. **Three authorities, never merged.** Each fact has exactly one owner; the others
   may display or cache it but never invent or overwrite it.

   | Fact | Authority | Evidence |
   |---|---|---|
   | Accounts, membership, permissions, a device's "contribution ON" | Lab Server; ON is valid only for the current agent boot | [CODE] `devices.py` poll (ON needs `desired` and the agent's own `contribution` flag; a new boot resets to OFF) |
   | Queued configuration and selected devices | Lab Server database, frozen at submit | [CODE] "Frozen assignment cannot change", `devices.py:408` |
   | Physical reservation and assignment epoch | Lab Server database, released only on agent evidence | [CODE] `devices.py:402-436, 472-484`; test `test_assignment_is_idempotent_and_outage_never_releases` |
   | Does a process exist / is it stopped | Device agent (PID + birth time, never PID alone) | [CODE] `platform_process.py`, `agent.py:owned_state`; unknown identity is "unknown", not "dead" |
   | Candidate acceptance, update coefficients, canonical model version | Coordinator ledger and verified weights (ADR-002) | [CODE] unchanged by this ADR |
   | Product status shown to users | Lab Server, derived from fenced agent reports | [CODE] `store.py:_dispatch_run` |
   | Artifact READY | Verified bytes plus a final manifest | [CODE] `local_storage.py`, `recovery.py` |

2. **One command path, unchanged:** user API → durable assignment/command → agent
   pull and ack → local coordinator/worker → fenced reports. The browser never
   supplies shell commands or executable paths. [CODE] test
   `test_shell_commands_and_bad_paths_never_execute`
3. **Lifecycle words are derived fields, not new database states.** *Queued*
   (recorded), *Assigned* (resources reserved, config frozen), *Adopted*
   (coordinator agent stored it), *Executing* (workers settled, run started),
   *Numerically finished* (final accepted update durable), *Released* (every owned
   process confirmed stopped, fresh report ≤30 s, for that assignment and epoch).
   Only *Released* frees resources. UI state names do not change.
4. **Lab Server outage contract — DECIDED 2026-10-12 (D4).** While the Lab Server is
   down, running computation keeps running. Starting workers, delivering cancel,
   recovery and release wait until it is back. Nothing relaunches automatically, and
   no replacement controller starts until the previous owner is known stopped.
   [CODE] worker start/stop/probe go through the Lab Server (`agent.py:92-106`,
   `devices.py: worker_command`). [MEASURED] one API outage of 40.055 s during a
   run (M2). The full partition matrix is [PENDING — ticket 3.1].
5. **Two additions** [PROPOSED]:
   - **Split the hold.** Today one flag (`dispatchHold`) makes the whole dispatcher
     return early (`store.py:206-208`), so while held, run status is not synced and
     cancel is not forwarded. Replace it with an *admission hold* (no new
     assignments) and an always-on *reconcile* (sync status, forward cancel/pause).
     Ticket 1.3.
   - **Operator verbs `fence` and `declare-lost`.** Admin only, mandatory reason,
     audited. `declare-lost` releases the reservations of an assignment whose device
     cannot report, and marks the run failed with "unconfirmed release". When that
     device reconnects its agent must stop any process of a released assignment
     (today it only records `released`, `agent.py:394`). Why: today one dead or
     returned machine blocks maintenance, backup and ownership changes for the
     **whole lab** (`devices.py:621-626`, `deployment.py:21-29`). Ticket 3.2.
6. **Restore never creates a second controller.** Restore into a new directory,
   keep reservations and the admission hold, reconcile with the agents, then let an
   operator release or resume. Identity and epoch rules are in ADR-007 (D5).
7. **Out of scope for the MVP:** active-active management, automatic cross-host
   coordinator failover, a portal that sends commands. One experiment runs per
   coordinator device at a time; disjoint devices may run in parallel through
   reservations [CODE]; simultaneous multi-GPU acceptance is [PENDING].

## Cancel and pause (unchanged)

Cancel is a durable request, then cooperative restore/drain. Pause stops only at a
completed-generation checkpoint, then drains and releases. Resume keeps the run and
its numerical lineage but gets a new epoch and new grants. An infrastructure failure
is never recorded as reward zero. [CODE] `test_pause_resume.py`

## Later (not designed)

If a portal is ever built, labs push read-only snapshots out. Commands from a portal
into a lab are a separate design and are not part of this ADR.
