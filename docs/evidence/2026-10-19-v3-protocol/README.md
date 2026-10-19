# Recipe v3 — worker protocol: texts submitted, scored on the coordinator, antithetic pairs run

Baseline: `135749e` (ledger schema 6 and record 2), branch `feat/extensibility-step0`. ADR-008 (accepted) sections 5 and 7.
Changed: `worker_api.py`, `worker.py`, `executor.py`, `coordinator.py`. `noise/`, `es/` unchanged. The Recipe v1/v2 paths
keep working: without a scorer the coordinator takes rewards as before, and without antithetic pairs the seeds are today's
`derive_seed(experiment, generation, index)` with sign +1.

## What changed

- **Protocol**: `submit_result` may carry `completions` + `completions_sha256` instead of `reward`. A coordinator built
  with a scorer accepts only texts, one without accepts only rewards (`rejected` otherwise). The hash must be that of the
  texts (`bad_request` otherwise). The attempt is checked before the scorer runs, so a stale or foreign report costs no
  scoring. A `ScorerError` is answered `scorer_failed` (new, fixed error code), kept as `scoring_error`, commits nothing.
- **Worker**: an evaluation that returns texts is sent with `submit_completions`; an empty or non-text list is a
  `VERIFIER_ERROR`, never sent.
- **Executor**: perturbs with `sign · σ` (sign +1 is today's perturbation bit for bit); with `return_completions` it returns
  the texts instead of the reward.
- **Coordinator**: `antithetic` (pairs, even population), `coefficient_rule` (version-2 records), `score(generation,
  descriptor, texts)`; a scoring failure stops the generation with `ScoringFailed` (no candidate is scored as 0).

## What the tests show

- Through real HTTP and worker threads (`tests/ledger/test_coordinator_v3.py`): without pairs, v3 gives exactly the child
  of today's `apply_es_update_` on the same seeds and rewards, with every candidate's texts stored and re-scorable to its
  committed reward; with pairs, the ledger holds (seed, +1), (seed, −1) and the child equals `apply_coefficients_` of the
  merged coefficients computed by hand; a broken scorer stops the run, commits nothing and the worker sees `scorer_failed`.
- The executor perturbs a −1 candidate with exactly `perturb_model_(…, −σ)`.

## Receipts

| Check | Result | File |
| --- | --- | --- |
| Full CPU product check | 22/22 PASS; runtime 2,214 passed, 100 skipped; backend 287 passed | `check-all.log`, `checks/` |
| Mutation check | control passes; 13/13 killed | `mutants.json`, `mutation.log` |

## What this does NOT show

No real model or GPU (toy FP16 model, toy texts and scorer), no audit scheduling (the ledger can record audits; nothing
re-runs candidates yet), no product runner, agent, backend, web or desktop change: the product still creates v1/v2 runs.
