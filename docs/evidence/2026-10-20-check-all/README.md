# Full CPU check at 38eb72b — 2026-10-20

`scripts/check-all.sh docs/evidence/2026-10-20-check-all/checks` started at `38eb72b` (all work of the opened
update formula, Countdown/GSM8K, evaluation chunk and Worker data folder). While it ran, `1720b7e` added only the
checkpoint-evaluation script and its tests (not in this run's runtime test count).

Result: 21 of 22 steps PASS; `worker-onboarding` FAILED at its build-name assertion: the committed
`desktop/worker/resources/defaults.json` names `lf1-20261019-r11-candidate1` (since `cb157f3`, after the last full
check at d415f68), which the pattern `lf1-YYYYMMDD-rN` did not allow. The pattern now also accepts `-candidateN`;
`checks/worker-onboarding-rerun.log`: PASS. Runtime and backend counts are in `checks/runtime-tests.log` and
`checks/backend-tests.log`.

## What this does NOT show

- CPU only; no GPU, Windows or packaged-installer run. Browser/Electron checks use fixtures.
- The failed step was rerun alone, not the whole suite again.
