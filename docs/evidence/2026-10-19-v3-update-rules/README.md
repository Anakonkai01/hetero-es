# Opened update formula: coefficient rules, alpha schedule, momentum — 2026-10-19

Owner decisions of 2026-10-19 night (plan `~/.claude/plans/c-agents-md-v-jaunty-quasar.md`, Part A). The update is now
θ ← θ + α_t · Σ_{a<K} β^a · (1/n)Σ cᵢεᵢ, chosen per plan; the kernel `es/update.py apply_coefficients_` is unchanged.

## What this does

- `runtime/src/heteroes/v3/coefficients.py`: rules `zscore@1` (today's `standardize_rewards`, bit for bit),
  `centered-rank@1` (Salimans et al. 2017, ties share their mean rank), `python@1:<sha256>` (a researcher's
  `f(rewards)`, self-hosted coordinator only); truncated heavy-ball momentum written as ONE `apply_coefficients_`
  call over the joined seeds of the window (oldest first, each coefficient scaled by β^age · M / n_s).
- `generation_record.py` (protected; owner-approved): accepts the new rule names; a momentum record carries
  `update_rule` and `momentum_history` (merged seeds/coefficients of its K−1 predecessors, newest first), so replay,
  crash recovery and workers need nothing else. Documents without momentum have neither key: the pinned hash of an
  existing version-2 record is unchanged (`test_a_zscore_version_2_record_keeps_its_bytes`).
  `verify_coefficients` follows the record's rule and returns False (unchecked) for a python rule without its code;
  `replay.py` counts those as `unverified_coefficients`.
- Plan (`v3/documents.py`): `alpha` is a number (as before) or `{kind: constant|cosine|linear, initial, minimum}`
  (`alpha_at`); optional `update` (momentum: β exact float32 in (0,1), window 2–8); `coefficientRule` may be
  `centered-rank` or (allow_python only) `{name: python, version: 1, eta, codeSha256}`. The generation context
  gains `alphaFloat32` / `update` only for plans that use them, so earlier contexts keep their hashes.
- Coordinator: record alpha from the plan's schedule; momentum history from the ledger's earlier records; loaded
  python rule. Local runner/CLI: `"coefficientRule": {"kind": "python", "path", "function"}`, `alphaSchedule`,
  `momentum`. SDK: `ESConfig(alpha_schedule, alpha_minimum, momentum_beta, momentum_window)`,
  `ESTrainer(coefficient_func=...)`.
- Tests: `runtime/tests/v3/test_v3_coefficients.py`, `test_v3_update_rules.py` (tiny CPU model, real local runs with
  2 HTTP workers: every rule replays bit for bit from its records; momentum generation 0 equals the plain run's child;
  generation 2 equals α·(g2 + β g1 + β² g0) computed in float64 from regenerated noise within one FP16 step),
  `tests/test_generation_record.py`, `test_v3_documents.py`. Mutation: 26/26 killed (`mutation/result-py.txt`);
  the first run (`result-py-first.txt`) had 4 survivors, each closed by a test before the rerun.
- `protected-files.json`: `noise/`, `es/`, `ledger/`, `worker_api.py` unchanged since d8edc22.

## What this does NOT show

- No GPU run with these rules and no learning comparison yet; nothing says centered-rank or momentum helps.
- The managed lab (backend/web/product runner) does not offer them yet; python rules are never offered there.
- Momentum with a python rule or antithetic pairs is covered by the unit tests of the joined inputs, not by a run.
- Full `check-all` not run for this commit (v3, ledger and record suites: 1237+ passed earlier in this session).

## Managed lab and web (second commit)

Backend `Configuration` gains `alphaSchedule`, `alphaMinimum`, `momentumBeta`, `momentumWindow`, `evalChunk`
(`backend/constants.py V3_UPDATE_KEYS`; runs saved before them still dispatch), validated by the numpy-free
`heteroes.v3.options.validate_options`; `centered-rank@1` is accepted, python rules never. `product/v3.update_options`
maps them into the documents. Web `V3Fields`: coefficient rule, alpha schedule/minimum, momentum β/window, prompts per
call, and the `countdown` scorer fields; Vietnamese strings added. Backend 321 passed; frontend unit 78 passed, tsc,
eslint, i18n, Prettier clean; backend mutation 7/7 killed (`mutation/result-backend.txt`). No browser walkthrough.
