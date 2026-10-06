# ADR-002 — Candidate, attempt and lease: a durable ledger that keeps one result per candidate and one update per generation

- **Status:** Implemented and tested for one coordinator process (2026-10-06/07, steps G2a to G2f). This written ADR is a **draft by Claude, pending owner review**. The worker-facing protocol in section "Decision 9" is a **proposal, not implemented**.
- **Date:** 2026-10-07
- **Deciders:** A (Systems/Core owner)
- **Related:** [numerical-contract.md §3, §12, §13](../numerical-contract.md), [architecture.md §6 to §7](../architecture.md), MASTER §10 (the seven invariants), `src/heteroes/ledger/`, `src/heteroes/generation_record.py`

## Context

A generation of ES is N candidates evaluated by workers on different machines, and one update computed from their N rewards. Workers die, answer late, answer twice because an acknowledgement was lost, run the wrong version, or fail to restore their weights. The update must still use **exactly one reward per candidate, in a fixed order, and be applied exactly once**: a wrong or doubled reward does not crash anything, it silently moves the model in a direction nobody evaluated (the same kind of silent failure as the noise problem of ADR-001).

MASTER §10 states seven invariants: (1) at most one committed effect per candidate; (2) a retry is a new attempt of the same candidate; (3) a result commits only if its attempt, lease and version are valid; (4) a duplicate delivery after a lost acknowledgement creates no second reward; (5) a generation aggregates only when the expected set is complete, never "the first N results"; (6) a model version is used only after its update was published; (7) a worker whose restore failed is quarantined.

The ledger is the coordinator's memory of what was given to whom and what was accepted. It must survive a restart and must be testable without GPUs.

## Decision

1. **Three identities.** A **candidate** is the logical job (`CandidateDescriptor`: recipe, parent weights, experiment, generation, index, seed), the same for every worker and every retry. An **attempt** is one try at it (`candidate_id/aN`). A **lease** is the right of one worker to run one attempt until a deadline, proved by a random 128-bit **token**. Operational data (worker, attempt, lease, retry, time) lives only in the ledger; the descriptor has no field for it, so noise cannot depend on it.
2. **SQLite, rules enforced twice.** One file (WAL), schema version in `PRAGMA user_version`, no migration yet (version 5). Every rule is checked in Python (clear errors) **and** by the schema (primary key, foreign key, unique, check): at most one `result` row per candidate is a primary key, not an `if`. A writer that bypasses the Python code is refused by the database too.
3. **Leases expire lazily and are not hard deadlines.** Nothing runs in the background. A read reports a `LEASED` candidate whose deadline has been reached as `PENDING`; the next `lease` takes it as a new attempt. The deadline is half-open (a lease is over **at** the deadline). The **latest attempt may still deliver after its deadline** as long as nobody was given the candidate in the meantime: the lease is the right to be the only one, until replaced. The clock is injected (`time.time` by default, because deadlines are stored and compared after a restart; a monotonic clock starts again at every boot). A wrong clock can only waste work (a lease ends early, its worker's result is refused as stale), never make two attempts valid at once.
3. **Results.** The worker returns the **whole descriptor it ran**, its attempt number, its token and the reward. Checks, in this order, stop at the first failure and write nothing: reward is a finite number (not `bool`, not NaN/Inf; an invalid reward does not close the attempt) → the candidate exists → the descriptor equals the stored one (another seed, recipe or parent is a `ResultMismatchError`) → the attempt is the latest and the token matches (else `StaleAttemptError`) → already committed: the same reward is acknowledged (`ALREADY_COMMITTED`, nothing written), another reward is a `ConflictingResultError` → the attempt must still be open → the worker is not quarantined → commit (result row, attempt end time and candidate state in one transaction). A duplicate delivery is idempotent; a conflicting one is an alarm, never overwritten.
4. **Failures are typed and never a reward.** `report_failure(kind)` with `OUT_OF_MEMORY`, `VERIFIER_ERROR`, `RESTORE_MISMATCH` or `OTHER` closes the attempt, frees the candidate at once and counts against the retry budget (`max_attempts`, a parameter of the coordinator process, default 3). Reporting the same failure again changes nothing.
5. **Quarantine.** `RESTORE_MISMATCH` puts the **worker of that attempt** (read from the attempt row, never claimed by the worker) in a `quarantine` table in the same transaction: it gets no leases and its new results are refused (an already committed result is still acknowledged). Its other leases are not released at once; they run out. `release_worker` is a manual act of a human, never automatic. A repeated report of the same failure does not quarantine again.
6. **The state of a generation is computed, never stored.** `COMPLETE`: every candidate is committed. `FAILED`: a candidate has used all its attempts and its last lease is over (it can never commit). `OPEN`: otherwise (a last attempt that is still running keeps it open). A `FAILED` generation hands out no more leases. `get_generation_results` returns seeds and rewards **in index order** and only for a complete generation; otherwise it raises (never a part, never an invented reward). Because the state is computed, raising `max_attempts` and restarting turns a `FAILED` generation `OPEN` again.
7. **The update record is written before the weights are touched.** `GenerationRecord` (inputs only: experiment, generation, recipe hash, parent weights hash, seeds, rewards, **coefficients**, alpha) has a version and a hash; `record_update` accepts it only for a complete generation and only if it says exactly what was committed; there is one per generation (the same again is acknowledged, another is a `ConflictingUpdateError`: after a restart the stored one must be applied). `mark_applied(record_hash, child_weights_sha256)` records the outcome apart from the record (the child hash is not part of the record hash, which must not change after the fact). Because the update is deterministic, a **second, different child** for the same record is not a new fact but an alarm. If the coordinator crashes after the weights changed but before `mark_applied`, the record is still there and the update can be redone from the parent checkpoint. The restart procedure itself is not implemented.
8. **The coefficients travel; nobody recomputes them.** `apply_coefficients_` applies given coefficients (they must be exactly float32 values); `apply_es_update_` is standardization followed by it. See "Why the coefficients travel".
9. **Worker-facing protocol [P — proposed, not implemented].** The ledger methods are the coordinator's internal API. The workers pull (MASTER §7). Proposed mapping, to be settled with the first HTTP code:

   | Ledger method | Future endpoint | Request | Response |
   |---|---|---|---|
   | `lease` | `POST /v1/leases` | worker id, duration (the policy picks the candidate) | descriptor (`to_dict`), attempt number, token, deadline |
   | `submit_result` | `POST /v1/results` | descriptor, attempt number, token, reward | `COMMITTED` or `ALREADY_COMMITTED` |
   | `report_failure` | `POST /v1/failures` | descriptor, attempt number, token, kind | acknowledgement |
   | `get_update` | `GET /v1/updates/{experiment}/{generation}` | | record JSON, and the child hash once applied (replay mode) |

   Each `LedgerError` subclass becomes a stable error code (`already_leased`, `stale_attempt`, `result_mismatch`, `worker_quarantined`, `generation_failed`, `conflicting_result`, ...). `RUNNING` and heartbeats are not part of this ADR.

### Why the coefficients travel

`standardize_rewards` computes in float64 and casts to float32. When a reward **equals the mean** (common when rewards are k/96), `reward - mean` is 0 in exact arithmetic but, depending on the order in which the sum was made, the coefficient is `0.0` or a residue of about `1e-16`. Measured on this machine with random sets of rewards k/96: **0.3% of the sets** (59 of 20,000 for N = 8; 131 of 40,000 in a second run) gave different float32 coefficients for a different summation order; **every one** of the 131 classified cases was of this kind (zero against a residue below 1e-9), none a real float32 difference. On a synthetic update of 2 million elements (NumPy only, not the real `apply_es_update_`) no FP16 weight changed. So the weights are practically unaffected, but the **bytes of the coefficient vector are not**: if two machines each recomputed the coefficients and compared them or their hash, about 0.3% of the generations would raise a false alarm. Hence one computation, by the coordinator, and the vector travels with the record; the rewards stay in it only so that the coefficients can be audited (`verify_coefficients`, exact by default, with a tolerance for an audit on another machine). Not measured: two real machines (NumPy 2.4.5 and 2.5.2) giving different coefficients; the experiment above used shuffled orders on one machine.

## Alternatives considered

| Alternative | Pros | Cons | Status |
|---|---|---|---|
| **Hard lease deadline** (a result after the deadline is refused) | Simple rule | Throws away finished work when a lease was a little short, and the coordinator may not even have given the candidate to anybody else | Rejected: the latest attempt keeps the right until replaced |
| **Background reaper** that returns expired leases to the queue | Sooner reaction | A thread and its races; hard to test; the answer is the same because every decision checks the deadline anyway | Rejected: lazy recovery |
| **Store the generation state** (a status column) | Cheap to read | Can disagree with the candidates; a stored `FAILED` would stop a deliberate retry after raising the budget | Rejected: computed |
| **Monotonic clock** | Immune to wall-clock jumps | Starts again at every boot, so stored deadlines become meaningless after a restart | Rejected for stored deadlines; the clock is injectable |
| **Rewards are authoritative; add a standardization fingerprint to the self-test** | No change to `update.py` | Does not solve the false alarm: the fingerprint would test one summation order | Rejected by measurement |
| **Keep the update record in a file, not in the ledger** | No schema change | No write-ahead guarantee tied to the committed results; the "recorded or not" fact could disagree with the ledger | Rejected: the record is validated against the committed results |
| **Put `child_weights_sha256` inside the record** | One object | The hash of the record would change after the fact; no stable identity for exactly-once | Rejected: outcome kept apart |
| **Idempotency keys chosen by the worker** | Common in web APIs | The natural key (candidate, attempt, token) already exists and is checked | Not needed |
| **Ray / task-queue retries** | Mature | A transport retry that succeeds does not say whether the reward is valid: the stale-attempt, version and update-record checks are still needed (MASTER §23.8.3) | Not adopted |

## Consequences

- Correctness (one result per candidate, one update per generation) does not depend on the accuracy of any clock or on worker identity; only efficiency does.
- One coordinator process is assumed. `max_attempts` is a policy of the process, not stored: two processes with different values would disagree about `FAILED`.
- A sqlite3 connection belongs to the thread that created it; a threaded HTTP server will need one connection per thread (to be done with the first HTTP code).
- Worker ids are free strings: quarantine blocks that name, a worker that renames itself escapes it (acceptable while workers are trusted; `TODO.md`, group `ledger-next`).
- There is no migration: a ledger file of another schema version is refused.

## Evidence

All numbers are from the 5070 Ti box (Python 3.12, NumPy 2.4.5). The ledger has **not** been run on the 1660 SUPER (Python 3.14).

- Tests: the whole suite gives 978 passed and 14 skipped in about 30 s (the skips are the real-model tests, which need `HETEROES_QWEN_PATH`). They include: unit tests per function, a model of the contract that predicts every ledger action (the exact error class or outcome) and checks the tables directly, six scenarios of MASTER §22.4 plus a quarantine one on simulated time (SimPy), random schedules (Hypothesis; 3,000 examples per test with `HETEROES_HYPOTHESIS=fuzz`, no failure), every order of small alphabets (32,706 sequences by default; 113,866 in 88 s with `HETEROES_EXHAUSTIVE=deep`; no failure), and two dispatch policies on unequal workers (greedy, wave).
- Mutation checks by hand on scratch copies (deliberate faults in the code; not automated in CI): see STATUS for the counts per step. Every fault was caught except equivalent ones (a pragma that Python already makes redundant; `BEGIN IMMEDIATE`, see below). Several gaps in the tests themselves were found this way and closed.
- Measured: a record of 8 candidates is 690 bytes (1.9 KB for 32, 7 KB for 128) against a 0.99 GB FP16 model.

**Not verified:**

- Races between two writers (the code takes the write lock with `BEGIN IMMEDIATE` before reading; no test uses two threads, and removing that line changes no test). The constraints would turn a lost race into an exception, not silent corruption; this is reasoning, not an experiment.
- Behaviour on Python 3.14 / the 1660 SUPER, and with a threaded server.
- The restart reconciliation (comparing the weights hash with parent and child, restoring and redoing); only its data is in the ledger.
- Whether two real machines compute the same coefficients (see above); and the effect of the coefficient residue on the real model (only a synthetic test).
- Any claim about speed or scheduling: the simulated times of the dispatch tests describe a model, not the GPUs.
