# Tail-aware scheduling, liveness and elastic membership: CPU gate ALL PASS

Predeclaration: [README.md](README.md). Design: [ADR-009](../../../runtime/docs/adr/ADR-009-scheduling-and-elastic-membership.md).
Branch `feat/r11-scheduling-elastic`. The CPU gate was run alone at `37723d6` with `scripts/check-all.sh` into `checks/`.

| Gate | Result |
| --- | --- |
| Combined check | **23/23 ALL PASS** (`checks/*.log`) |
| Runtime tests | 2574 passed, 102 skipped |
| Backend tests | 392 passed |
| Web / Worker unit tests | 91 / 88 passed |
| Browser and Electron probes | onboarding, live, experiments, model qualification, showcase, page audit, Worker onboarding and station: PASS |

## Commits

| Commit | Change | Findings |
| --- | --- | --- |
| `44e27fc` | ADR-009 and this predeclaration | |
| `dd875c6` | `AdmittedOnly` forwards hooks and its members can change; heartbeats keep workers alive for GreedyTail; `SpeedBook.from_ledger` | F2, F3, F4 |
| `a34c45f` | `greedy-tail` (default) and `greedy` offered through runner, supervisor, backend, web and `heteroes serve --scheduler`; dead names removed; heartbeat-aware stall; generation/audit limits derived from measured speeds; audits chosen and completed in each summary | F1, F5, F7, F8, F9 |
| `d148231` | Elastic membership | F6, F10 |
| `37723d6` | `privateLabUrl` only through the signed-in capabilities; desktop keeps the sanitised stack of an unclassified action failure | F11, F12 |

`d148231` (elastic membership) covers:
- **Ledger:** additive `membership` and `expiry` tables, schema 6 kept.
- **Runner:** `product/membership.py`, with per-device credentials swapped as a whole.
- **Agent and supervisor:** agent `UPDATE_MEMBERSHIP`; the supervisor starts joined workers and stops left ones.
- **Lab endpoint:** `POST /api/v1/experiments/{id}/workers`, with submission-grade eligibility and reservations.
- **Lab behaviour:** `allowJoin` auto-join; contribution OFF leaves instead of cancelling.
- **Web:** a members panel.

Key invariant (`runtime/tests/ledger/test_elastic_membership_e2e.py`, real HTTP workers on CPU):
- **Membership changes over the run:** w1 alone; then w2 joins at generation 1; then w1 leaves at generation 2. A
  non-member keeps asking for work throughout.
- **Weights:** the final weights equal the hand-computed update for 4 generations.
- **Ledger:** members per generation are recorded as declared, and `membership_violations` is empty.
- **Non-member:** it never committed a result.

## Mutation checks (scratch copies, `mutation/`)

| Step | Mutants | Killed | Survivors fixed by a new test |
| --- | --- | --- | --- |
| 1 dispatch | 7 | 7 | durations of a failed-then-retried candidate |
| 2 product policy | 8 | 8 | `runner-drops-admission` → `test_runner_scheduling.py` |
| 3 liveness/limits | 9 | 9 | incomplete audits → `test_audits_that_could_not_run_show_in_the_summary` |
| 4 runtime membership | 16 | 16 | none |
| 4 backend membership | 12 | 12 | `auto-join-readds-left`, `auto-join-ignores-flag` (the check moved into `auto_join`), `off-cancels-anyway`, `resume-forgets-joined` |

Two operator mistakes in the mutation runs are recorded and do not change the counts above:
- **Incomplete copy:** the first step 2 run used a copy without `scripts/`, so runner mutants were "killed" for the
  wrong reason. That run was redone on a full copy, where one mutant survived and got a test.
- **Hang:** the first step 3 run hung on a mutant, because that test had no stall backstop. The test now has one, and
  `mutate.py` has a per-mutant timeout.

## Retained unexplained observations

- **`test_v3_product[hf_fp32_cpu_guard_v1-space0]` failed once.** This was in a full runtime run made while step 3
  source files were being edited; the test starts subprocesses that import the source. The isolated rerun passed
  15/15, and three later complete runs pass. The traceback was not kept, so the cause is not proven.
- **The desktop Worker unit suite failed once in 7 runs** (87/88). The test name was not captured, and 6 later runs
  pass 88/88.

## What this does NOT show

This is not GPU, multi-machine or installed-package evidence. Candidate7 packages, device upgrades and the redeclared
50-generation acceptance with a real join/leave and outage are the next steps. It makes no speed or learning claim.
No public lab, main branch, push or release change.
