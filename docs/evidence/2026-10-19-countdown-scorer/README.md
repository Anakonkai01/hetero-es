# Countdown scorer and dataset builder — 2026-10-19

Plan: `~/.claude/plans/c-agents-md-v-jaunty-quasar.md` steps 2–3 (owner decisions of 2026-10-19 night).

## What this does

- `runtime/src/heteroes/v3/scoring.py`: declarative scorer `countdown@1`, config `{numbersField, targetField}`.
  Reward of TinyZero / "Evolution Strategies at Scale" (arXiv 2509.24372): 1.0 when the expression in the LAST
  `<answer>…</answer>` uses every given number exactly once and equals the target; 0.1 for any other answer
  (wrong value, wrong numbers, syntax error, division by zero, power, unary minus, non-integer); 0.0 without an
  answer. The expression is parsed with `ast` and evaluated with `fractions.Fraction` (exact); Python never
  evaluates it. Scoring is on the coordinator only: workers need nothing new.
  Spec validation now checks every `*Field` key as a nonempty column name.
- `backend/validation.py`: a v3 draft requires every `*Field` column of the scorer config in the dataset (it
  checked only `answerField`, so `countdown` would have been refused).
- `runtime/scripts/build_countdown_dataset.py`: seeded subset of the pinned `Jiayi-Pan/Countdown-Tasks-3to4`
  file (revision `408f70d1…`, SHA-256 `a1b37bea…`), TinyZero's instruct prompt, columns `prompt`, `nums`
  (space-separated text: v3 columns are scalar), `target`, `sourceIndex`. The dataset card declares **no
  license**, so rows are not committed; `countdown-2500.jsonl.meta.json` is the identity of the 2500-row file
  built for the pilot (`fileSha256 ecdd37e1…`, 934 KB, under the lab's 3 MB import limit).
- Tests: `runtime/tests/v3/test_v3_scoring.py` (countdown cases), `runtime/tests/v3/test_countdown_dataset.py`,
  `backend/tests/test_v3_study.py` (missing/present scorer columns). Mutation: `mutation/` — 12/12 runtime and
  2/2 backend mutants killed; the first runtime run had 3 survivors (float division, power reaching the
  target, `7.0` as a number), which got tests before the rerun.

## What this does NOT show

- No model was run: nothing here says Qwen learns Countdown, or what reward the base model gets.
- Not compared with TinyZero's own reward function on real texts; the 0.1/1.0 rule is reimplemented from its
  description, with stricter syntax (no unary minus, integers only).
- The web form does not offer `countdown` yet (done together with the coefficient-rule fields).
- Full `check-all` not run for this commit; v3 runtime tests (113 + 4) and backend v3 tests passed.
