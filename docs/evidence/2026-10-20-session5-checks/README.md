# Session 5 full check (2026-10-20)

`checks/` is the first full `scripts/check-all.sh` across the combined session 4 + session 5 code (at cfb07cc+6e0c596).
It FAILED three steps, all real and all from earlier commits that only ran focused suites:

- `source-packages`: the Lab Server source package lacked `heteroes/product/cpu_coordinator.py`, which the backend
  imports since 66d3fe7, so a packaged Lab Server could not start. Fixed by adding it to `backend/runtime_sources.py`
  (the shared-runtime subset test failed for the same reason).
- `backend-tests`: `test_device_configuration` still expected a role change to an 10999 MB coordinator to be refused;
  the owner's any-GPU coordinator decision (ff226fd/66d3fe7) removed that limit. The case now checks a GPU profile with
  0 MB VRAM, which the model validator still refuses.
- `web-experiments`: the browser check still looked for the label "Declarative scorer", renamed "Scorer" in efe8e33.
  `web-experiments-rerun1-exact-label.log` shows an exact-label locator also failing (the select's accessible name
  includes the chosen option); the check now finds the combobox whose name starts with "Scorer";
  `web-experiments-rerun.log` passes.

`checks-final/` is the clean rerun after these fixes.

## What this does NOT show

CPU fixture checks only: no packaged build, GPU, Windows, real lab or managed CPU-coordinator acceptance.
