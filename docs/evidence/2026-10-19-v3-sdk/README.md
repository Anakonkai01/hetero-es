# Recipe v3 SDK/CLI polish and final combined CPU checks — 2026-10-19

Source commit `e35811c`. The installed `heteroes` console command and
`python -m heteroes` delegate to the same runner as `python -m heteroes.v3`.
Runnable full/LoRA keyword-reward examples and execution/identity guidance are in
runtime/examples/v3 and runtime/docs/v3-local-runs.md. Python scorers are explicitly
trusted coordinator code, not sandboxed; imported helper dependencies need their
own reproducibility records. Managed-product documentation now reflects audits,
complete v3 recovery and the separate GPU qualification.

## Completed receipts

- `check-all.log`: **22/22 ALL PASS**, completed before this folder was committed.
  Detached `/home/pc5070ti/projects/heteroes-v3-recovery-check` at **e35811c**.
- `checks/runtime-tests.log`: **2,273 passed, 100 skipped**.
- `checks/backend-tests.log`: **302 passed**.
- All remaining checks pass: lint/format, i18n, source-package imports, web/desktop
  units, types, builds and browser/Electron contracts against disposable labs.
- `tests-latest.log`: **10 passed**, both module entry points actually train with
  relative spec paths; the installed metadata's entry point shows help in a fresh
  process without importing Torch. Existing scorer, local run and audit tests pass.
- `install.log`, `installed-help.log`, `installed-run.log`: a wheel was built from
  a scratch source copy, installed into a new isolated venv inheriting the verified
  runtime dependencies, and the actual installed console command completes a tiny
  CPU generation. No existing Conda environment was changed. The example is a
  mechanics check with zero reward, not a learning result.
- `mutation.log`: **2/2** entry-point mutants killed. `tests-first.log` preserves
  the absent-module/absent-console-registration failures before implementation.

## What this does NOT show

No new optimizer/update-rule plugin, arbitrary sigma callback, native Windows,
r11/installer acceptance, package publication, live deployment or learning benefit.
The package still expects separately installed numerical/model dependencies; this
receipt proves installation into a prepared environment, not a new dependency
resolver or an end-user desktop runtime profile. Full/subset/LoRA and existing
sigma schedules are configurable; broader research hooks remain deferred.
