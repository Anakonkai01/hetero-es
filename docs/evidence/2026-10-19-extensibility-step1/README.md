# Extensibility step 1 — ADR-008 draft and the pure Recipe v3 functions

Baseline: `acbe02c` (end of step 0), branch `feat/extensibility-step0`. The owner asked to continue past step 0 with whatever
does not need them. This step writes the ADR-008 draft and only the parts of it that are new, pure modules: nothing in
`noise/`, `es/`, `ledger/`, `generation_record.py`, the worker protocol or the executor changed, and nothing calls the new
modules yet.

## What changed

- `runtime/docs/adr/ADR-008-recipe-v3-and-extensible-experiments.md` (DRAFT): recipe / plan / generation-context split,
  weight spaces as a trainable schema T, antithetic pairs merged into unique seeds, coordinator scoring, ledger schema 6,
  one format break with read-only translation of v1/v2, and four open questions (Q-A … Q-D).
- `runtime/src/heteroes/v3/documents.py`: strict Recipe v3 and plan validation and hashes (every field explicit), FP32
  sigma schedule, translation of v1 and v2 documents.
- `runtime/src/heteroes/v3/scoring.py`: declarative scorers (the three existing rules reused exactly, plus regex,
  exact-string, choice-letter), Python scorer identity by code hash, failures as `ScorerError` (never a reward of 0).
- `runtime/src/heteroes/v3/antithetic.py`: (seed, sign) of each candidate and the pair merge
  `float32((float64(c+) − float64(c−)) / 2)`.
- `runtime/scripts/translate_recipes_v3.py` → `v3-mapping.json`: the eight recorded v1 recipes, their recorded hash and
  their v3 hash (8 distinct), with the files they came from.

## What the tests show

- `last-integer@1` reproduces every per-record reward and mean reward written by the recorded arith16 probes and
  regressions; `answer-line-integer@1` gives exactly what today's `evaluate_cot` gives on the 9 × 128 recorded CoT texts
  of `2026-10-09-chunk128` (generation replaced by the stored texts).
- The frozen perturbation code with scale −σ gives the exact bitwise negation of +σ, and equals the FP32 rule with negated
  noise element by element; `apply_coefficients_` with merged pairs lands within one FP16 spacing of the signed sum over
  all candidates (a merge without the halving fails this).
- Every recorded v1 recipe translates with its model, schema, noise, sigma, precision, decoder and workload hash; a v2
  recipe translates with the same FP32 sigma at every generation; the eight translated hashes are frozen.

## Receipts

| Check | Result | File |
| --- | --- | --- |
| New v3 tests | 37 passed | `checks/runtime-tests.log` (part of the full run) |
| Full CPU product check | 22/22 PASS; runtime 2,156 passed, 100 skipped; backend 287 passed | `check-all.log`, `checks/` |
| Mutation check, first run | control passes; 22/25 killed | `v3-mutants.json`, `v3-mutation.log` |
| Mutation check, after three new tests | control passes; 25/25 killed | `v3-mutation-final.log` |

The first run's three survivors were gaps in the tests: a regex with several groups, `casefold: false` on its own, and
scorer exceptions other than `ZeroDivisionError`. Each now has a test.

## What this does NOT show

No GPU computation, no run of a v3 experiment and no replay from translated documents (the runner, ledger, worker protocol
and executor do not use the new modules yet). Equality of texts across machines is not shown here. The ADR is a draft: its
rules are proposals until the owner accepts it, and the mapping table is a preview that would be regenerated at the switch.
