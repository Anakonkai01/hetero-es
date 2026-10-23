# Long-run monitoring repair — 2026-10-23

The owner requested a direct review of the 600-generation completed soak and the
900-generation failed soak, including stale status text, audit totals, timeline
and live replay. This follows the connector/name repair in
`../2026-10-23-live-connectors/`.

## Verified findings

- Completed run `44e65d7b2975447fa15fe85f115bad92` retained a stale shutdown
  failure in the product body although its final snapshot explicitly cleared it.
- The ledger has 720 completed matched audits. Recounting the canonical v3
  candidate addresses gives **722 selected audits**, not 719. The coordinator's
  `generation_done` log for generation 62 is missing after recovery. The separate
  `audit_incomplete` event records **two timeouts at generation 63**. Thus 720/720
  matched completed audits does not establish complete selected-audit coverage.
- The lab snapshot retains all 600 generation summaries but only 144 candidate
  attempts from zero-based generations 594–599. Counting those attempts as whole
  run totals showed incorrect progress. GPU-level counts from those attempts are
  only counts for the available detail window.
- Failed run `f10720536eba436ba026d650edbb6f16` completed 60 of 900 generations
  before disk exhaustion. It has 69/69 completed/selected audits and 28 retained
  generations of candidate detail. Its final uncommitted update must not animate
  indefinitely as though the run were still working.

`ledger-comparison.json` compares the reporting projection against read-only
canonical ledger queries for both runs, preserving the original reported totals.
The corrected projection does not rewrite stored run bodies, snapshots or ledgers.

## Repair

- Project the explicit final failure state on reads and propagate explicit clears
  on future updates. Keep the genuine disk-full failure.
- For managed v3 runs, count the fixed default 1/20 audit selection over committed
  canonical candidate addresses. Candidate IDs use `run/gN/cN`, independently of
  the candidate seed namespace. If generation coverage is insufficient, report
  selection as unknown rather than fabricate or clamp its denominator.
- Show 720/722 and two incomplete audits as a warning; show quarantine count zero.
- Use completed generation summaries for whole-run candidate totals. Stop worker
  activity and update animation after a terminal run ends.
- Open partial historical replays at their stopped end, with a button to replay
  the available candidate detail. Label the detail window and scope GPU statistics
  explicitly to that window.
- Offer available-history and entire-run Gantt ranges, with spaced generation
  labels. Keep reward-axis labels inside their SVG and limit their density.
- Show recorded device names in the candidate inspector as well as live GPU rows.
- Request a run's event history before applying the server's event limit, rather
  than filtering a globally limited event list in the browser.

## Validation

- `backend-before.log` / `frontend-before.log`: regressions fail before the fix.
- `backend-tests.log`: **439 passed** (one existing Starlette deprecation warning).
- `frontend-tests-final.log`: **98 passed**.
- `backend-mutation-final.log`: all three reporting mutants killed on scratch
  copies. The earlier control failure lacked the runtime package in the scratch
  copy; it is retained in `backend-mutation.log`.
- `frontend-mutation.log`: both replay/total mutants killed on scratch copies.
- `browser-reviewed/receipt.json`: both recorded runs accepted in a disposable
  CPU-only fixture lab at 375/768/1440px, including totals, audit coverage, stopped
  worker state, scoped history and readable chart labels.
- `build-reviewed.log`, `lint-reviewed.log`, `python-lint-final.log`,
  `i18n-reviewed.log`, `format.log`: type/build, lint, translations and source
  formatting pass. The initial JSX label-placement lint failure is retained.
- `public-before/`: read-only public browser captures before this second repair.

Browser fixtures were sanitized read-only copies of the existing snapshots,
preserving run IDs so deterministic audit selection remains the same. They were
served using a disposable test lab with fake installers and synthetic accounts.

## What this does NOT show

- No new GPU work, worker release, learning experiment or numerical replay was run.
- The two timed-out audits have not been retroactively executed. Reporting their
  true coverage is not a repair of the timeout/recovery behavior.
- Partial monitoring is not a full per-candidate replay of all 600 generations.
  Full canonical ledgers remain separate from the bounded web snapshot.
- The oomd root cause, memory-pressure mitigation and deferred low-disk acceptance
  remain open. No original overnight evidence was edited.
- Public deployment needs its own receipt and post-deployment browser checks;
  local fixture checks alone do not establish that the public site changed.
