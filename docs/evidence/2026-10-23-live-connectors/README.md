# Live-run connector and GPU-label repair — 2026-10-23

The owner reported that the new live diagram's wiring looked worse than the old
diagram, and that the GPU table exposed `cli-*` / `desktop-*` identifiers instead
of identifying the machines.

## Changes

- Restore direct, symmetric curved connections to the first row of GPUs.
- Route lower rows around their nearest outside edge with rounded corners and
  keep packets on the same route as the visible wire.
- Reuse precomputed routes while animating the diagram.
- Show the device name and GPU model in the table; keep internal worker IDs in
  tooltips. Preserve the ID fallback when no human-readable identity is available.
- Remove the NVIDIA vendor prefix from card subtitles so `RTX 5070 Ti` / `RTX 3060`
  remains visible instead of truncating the model after `NVIDIA GeForce RTX…`.

## Verification

- `geometry-before.log`: the two new routing regressions failed before the fix.
- `geometry-after.log`: all nine geometry tests pass, including sampled route and
  packet positions staying outside GPU cards for up to 16 workers.
- `mutation.log`: control passes; all three geometry mutants killed on scratch
  copies with `scripts/mutation-check.py`.
- `frontend-unit.log`: 96 frontend tests pass.
- `build-final.log`, `lint.log`, `i18n.log`, `format.log`: production type/build,
  frontend lint, translation and changed-source formatting checks pass.
- `browser-before/`: current-source baseline with the leftward detours and raw-ID
  table. Browser regression fails on the device label as expected.
- `browser-after/`: intermediate fix; its initial multi-row probe failed because
  reloading the page returns to the default tab. Retained without modification.
- `browser-final/receipt.json`: final fixture browser acceptance passes. Includes
  direct visible SVG paths, table names/models/ID tooltips, eight-worker layout,
  375/768/1440px viewports, reduced motion and no page errors.
- `before.png`: exploratory capture from the pre-existing local build, which still
  had the old curved diagram. It is not the current-source baseline.

The three-worker identity probe substitutes synthetic names and the owner's
reported raw ID shapes into a recorded fixture timeline. The eight-worker layout
adds synthetic idle workers; these are browser fixtures, not GPU experiments.

## What this does NOT show

- No new GPU run, numerical acceptance, throughput measurement or learning claim.
- No changes to worker contributions, run data, memory policy or coordinator
  recovery behavior.
- Fixture browser screenshots alone do not establish public deployment. Public
  publication and verification receipts are recorded separately when completed.
