# 2026-10-19 — phase 2: retire the loopback/SSH runtime

Baseline: handoff commit `8f9ae95` on `refactor/cleanup`. All work and checks ran in the working tree or temporary
copies. The deployed clone, its configuration and database, and the published r10 installers were not changed.

## Changes and preserved behavior

- `backend/errors.py` owns `RuntimeRejected`. The old backend HTTP adapter, serial dispatcher, mode branches,
  fake runtime and integration launch scripts are removed. Production startup requires an explicit private
  directory and `deploymentMode: agent`; factory errors still release the database writer lock.
- The import graph exposed a missing detail in the original handoff: `AgentManager` inherited `gateway.Manager`.
  The live coordinator supervisor, configuration validation and ledger projection moved into `run_supervisor.py`.
  Its three lifecycle hooks are implemented by `AgentManager`; the loopback HTTP server, SSH launching, worker
  registry and M1 whole-runtime backup are removed. The agent → runner → coordinator/dispatch path remains.
- Existing supervisor, process identity, WSL, quarantine, external-volume and ledger-projection tests remain.
  Former gateway tests now use a real `AgentManager` in `test_run_supervisor.py`.
- The web always shows agent-mode devices, coordinator selection, backup policy and study assets.
  Health keeps `agentMode: true` and `deviceConfiguration: true` for the shipped r10 apps.

## Test counts and deliberate removals

| Suite | Before | After |
| --- | --- | --- |
| Backend | 271 passed | 274 passed |
| Runtime | 2,115 passed, 100 skipped | 2,110 passed, 100 skipped |
| Frontend unit | — | 74 passed |
| Worker unit | — | 81 passed |
| Server unit | — | 1 passed |
| Product UI unit | — | 5 passed |

Backend deleted `test_agent_database_cannot_be_opened_by_legacy_dispatcher`: the legacy dispatcher no longer exists.
Four factory cases were added (explicit configuration, legacy/missing mode rejection and lock release, r10 health
capabilities and device routes), giving 271 − 1 + 4 = 274.

Runtime deleted only the five tests in `test_product_backup.py`, for the retired M1 backup API:

- `test_maintenance_refuses_active_and_unknown_shutdown`
- `test_snapshot_requires_hold_preserves_history_and_excludes_process_identity`
- `test_runtime_snapshot_rejects_symlink_sources`
- `test_retiring_transfer_archive_keeps_original_run_evidence`
- `test_unknown_coordinator_identity_blocks_maintenance`

Their maintenance/archive API is removed. Agent drain/ownership, generation recovery points and local storage
remain covered by their existing suites. The supervision tests moved to `test_run_supervisor.py` were retained,
giving 2,115 − 5 = 2,110. `httpx` remains a TestClient dependency.

## Receipts

- `backend-before.log`, `runtime-before.log`: fresh baseline before production edits.
- `factory-red.log`, `supervisor-red.log`: factory regressions and the missing extracted module fail before the
  implementation. `backend-focused.log` records an intermediate unindent error that dropped the pause decorator;
  it was restored before the full passing suite. `supervisor-focused.log`: 51 passing focused runtime cases.
- `check-all.log` and `checks/`: the CPU product suite, including types, lint, i18n, real web/Worker builds,
  fixture browser flows and Electron checks. The page audit checks 38 pages across Vietnamese/light/desktop and
  English/dark/mobile; zero overflow, page problems or untranslated strings.
- `runtime-after.log`: full runtime CPU suite. GPU-specific tests are skipped.
- `backend-mutation.log`, `runtime-mutation.log`: 4/4 mutants killed in each scratch copy, after passing controls.
  They cover rejecting legacy config, r10 health compatibility, active reconciliation, truthful rejection,
  confirmed drain, quarantine, bounded recovery and frozen configuration. Mutant definitions are adjacent JSON.
- `source-proof.json`: eight retained supervisor method ASTs unchanged; initialization/submission differ only by
  removed registry cache/legacy maintenance hold. Agent AST unchanged except its base import/name; dispatcher AST
  unchanged after the rename. Workloads are unchanged. All 15 frozen numerical source files are byte-identical.
  `runtime-imports-before.json` and `runtime-imports-after.json` preserve the dependency closures.
- `packaged-sources.log`: both refresh scripts ran on a scratch copy with unchanged dependency pins. The Worker
  archive contains `run_supervisor.py`; the Server contains `errors.py`; retired modules are absent. Isolated
  interpreters imported both extracted source archives without loading torch.
- `public-lab-readonly.json`: public health/pages and manifest pass; published build remains `lf1-20261014-r10`.
- `deployed-lab-readonly.json`: three live services alive, database quick check `ok`, deployed commit still
  `79876cb`, working `main` still `c2e18d0`. `5070ti` is APPROVED. **`3060-thao` is REVOKED**, contrary to the
  old handoff; its audit records `DEVICE_REVOKED` at `2026-10-14T07:04:51.110750+00:00`. This work did not change it.

## Reproduce the additional checks

From the repository root:

```bash
python3 docs/evidence/2026-10-19-phase2-runtime-removal/verify-sources.py
.venv-backend/bin/python -I docs/evidence/2026-10-19-phase2-runtime-removal/check-packaged-sources.py
.venv-backend/bin/python -I scripts/mutation-check.py --repo . \
  --copy backend --copy desktop/worker/resources/reference.json --env CUDA_VISIBLE_DEVICES= \
  --test "$PWD/.venv-backend/bin/python -m pytest backend/tests/test_agent_factory.py backend/tests/test_api.py backend/tests/test_admission_hold.py -q" \
  --mutants docs/evidence/2026-10-19-phase2-runtime-removal/backend-mutants.json
.venv-backend/bin/python -I scripts/mutation-check.py --repo runtime \
  --copy src --copy tests --env CUDA_VISIBLE_DEVICES= --env PYTHONPATH=src \
  --test "$HOME/miniforge3/envs/heteroes-match/bin/python -m pytest tests/ledger/test_run_supervisor.py tests/ledger/test_large_data.py -q" \
  --mutants docs/evidence/2026-10-19-phase2-runtime-removal/runtime-mutants.json
```

## What this does NOT show

- No GPU job, native Windows run, remote worker poll, new installer or deployment acceptance.
- Browser/Electron evidence uses synthetic fixture services and recorded runs, not live training.
- The packaging check builds source tarballs with a minimal web fixture and imports them; it does not run
  electron-builder or install an app. The real frontend build is covered separately by `check-all.sh`.
- The public check skips installer downloads and authenticated pages; it does not re-verify installer hashes.
- Phase 3 mock/cloud/dead-code removal and phases 4–6 remain pending. Historical integration guides are marked
  retired; their final consolidation belongs to phase 6.
