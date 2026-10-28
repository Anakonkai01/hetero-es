# D11 stage watchdog and explicit hard cap (M2), 2026-10-27

Decision D11 (ADR-012): watchdogs follow real progress; a heartbeat proves contact, not useful work; a finite hard cap
is configured explicitly.

## What changed

- `heteroes/progress.py`: a per-process counter. The executor advances it after perturb and restore,
  `study/evaluation.generate_rows` after every `generate()` chunk.
- The coordinator's job now says `progressReporting: true`. A worker that sees it adds `progress: {stage, units}` to its
  heartbeats (never otherwise: older coordinators refuse unknown fields). The API counts such a heartbeat as activity
  only when the units grew; otherwise it is liveness. A heartbeat without the field (a worker older than this) keeps
  the ADR-009 meaning, so deployed desktop workers are not stopped by the new rule.
- Hard cap: `Coordinator(generation_clock_path=...)` writes each generation's first wall-clock start to a JSON file and
  counts the cap from it, so a coordinator restart never extends the cap. The product runner uses
  `<run>/generation-clock.json`.
- New operational settings (outside numerical recipes): `hardCapSeconds` (60 s to 7 days, bounds the measured-speed
  limit) and `stallSeconds` (30 s to 7 days, shorter than the cap). Validated in `v3.options.validate_watchdog`, accepted
  by the backend request model and templates, used by `product/runner.py`.

## Checks

- `tests/ledger/test_stage_watchdog.py` (14) and `tests/v3/test_v3_progress.py` (3): growing units keep a long candidate
  alive; a hung computation with heartbeats stalls with the model untouched; legacy heartbeats keep their meaning;
  malformed progress is refused; progress is sent only when asked; the cap counts from the first start across a
  restart; settings bounds; executor stages and one unit per chunk.
- Mutation: [checks/mutation-01.log](checks/mutation-01.log) **11 of 11 killed** (`acceptance/mutants/watchdog.json`); the
  first run's survivor (malformed units hidden by a later descriptor error) is kept in `mutation-00-initial-survivor.log`.
- CPU: `tests/ledger`, `tests/v3`, `test_e2e_local.py`: 1576 passed, 7 skipped; backend: 452 passed.

## What this does NOT show

No lab UI field yet for the two settings; no long real run under the new rule; a single generate() chunk longer than
`stallSeconds` would still be reported as a stall (progress is per chunk, not per token).
