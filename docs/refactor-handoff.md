# Refactor handoff (2026-10-19) — phase 4 complete

The owner asked for one repository and a professional cleanup. Talk to the owner in Vietnamese, simply. Rules are in
`../AGENTS.md`: never push or tag, no Co-Authored-By, tests first plus a mutation check, the lab is touched only through
`scripts/local-lab.py`.

## State
- Single repository `~/projects/heteroes`. Runtime in `runtime/`, product at the root, both histories kept (old branches
  `archive/*`). Old folders are in `~/projects/_old/` (see its README).
- `main` (c2e18d0) = merge + path fixes + evidence `docs/evidence/2026-10-19-one-repo/`.
- The lab runs from `~/.local/share/heteroes-lab/app` (a clone of `main` at 79876cb, venv `~/.local/share/heteroes-lab/venv-backend`).
  Do not update it during the cleanup. The owner restarts the unit himself, because the auto-mode classifier blocks
  `systemctl --user restart heteroes-lab`.
- Work branch `refactor/cleanup`. Done so far, every commit green:
  `0245bd6` backend tests run in agent mode (`backend/tests/conftest.py` fixtures `lab`/`setup`, helpers in `labkit.py`);
  `a930622` M1 backup bundle and `/contributions` routes removed (backend + web);
  `d200085` fixture lab `scripts/serve-test-lab.py` runs in agent mode with two paired devices.
  At d200085: backend 271 passed, runtime 2,115 passed / 100 skipped, `check-all.sh` ALL PASS.
- This checkpoint completes phase 2: backend 274 passed; runtime 2,110 passed / 100 skipped;
  8/8 scratch mutants killed. Full receipts and source/packaging checks are in
  `docs/evidence/2026-10-19-phase2-runtime-removal/`. The live deployment and published r10 are unchanged.
- Read-only live check at this checkpoint: all three services alive, database quick check `ok`, `5070ti` APPROVED.
  **`3060-thao` is now REVOKED**, unlike the older handoff. No device state was changed during this cleanup;
  do not approve or re-enable it based on the old document.
- The owner's decisions (do not reopen them):
  - remove web mock mode;
  - remove the legacy control mode (D1);
  - delete cloud code, which stays recoverable from history;
  - rename the live local "cloud" storage code, but keep the SQLite table names;
  - ruff + prettier formatting for the WHOLE repository, Recipe v1 numerics included, with an AST-equality proof;
  - publish no new installer during the cleanup (r11 comes with the installer polish).

## Phase 2 completed; details that matter for the next change
- `RuntimeRejected` now lives in `backend/errors.py`. The legacy backend adapter, dispatcher, mode guards,
  integration launch scripts and fake `tests/test_api.py::Runtime` are removed. The factory requires an explicit
  `HETEROES_PRIVATE_CONFIG` and `deploymentMode: agent`; `backend.server` already supplies the directory.
- The old handoff incorrectly implied gateway was independent of the agent. **AgentManager inherited Manager.**
  Its live supervision/projection methods were extracted into `runtime/src/heteroes/product/run_supervisor.py`
  before deleting `gateway.py` and `product/backup.py`. Agent launch/worker-command hooks remain in `agent.py`.
  The retained methods have AST-equality receipts; the frozen numerical files are byte-identical.
- Gateway tests that exercise live behavior were moved to `test_run_supervisor.py`, using a real `AgentManager`.
  Only the five legacy backup tests were deleted. Backend removed one legacy guard test and added four factory cases.
- The web no longer branches on `agentMode`. **Keep health's `agentMode: true` and `deviceConfiguration: true`:**
  shipped r10 Worker/Server apps still check them. Unused mode fields in capabilities and operations were removed.
- `httpx` stays: Starlette's TestClient needs it. No runtime/profile tarball was changed in the working tree;
  source packaging was checked on a scratch copy. No installer was published and the live lab was not restarted.

## Next: phases 5-6 (full plan in Vietnamese: `docs/refactor-plan-vi.md`)
- **3. Mock mode, cloud and dead code — completed.**
  Receipts: `docs/evidence/2026-10-19-phase3/`. Backend 277 cases; 3/3 mutants killed.
  Runtime wire/table names beginning with cloud remain solely for compatibility.
  - Mock mode: `frontend/src/mocks/`, Mock* pages, `lib/dataSource.ts` and every `IS_MOCK` branch, msw,
    `static/mockServiceWorker.js`, `test:mock`, `LOCAL_BACKEND_HANDOFF.md`.
  - Routes without a caller: `GET /workspaces`, `/worker-registry`, `/platform/storage`, `PATCH /device/endpoints`,
    `/monitoring-events`, `/my-workers`, `/my-resource-submissions`, and the 501 catch-all. Before removing a route,
    check that the shipped r10 runtime tarball does not call it.
  - Cloud: `S3Backend`, the `storageFile` branch, `requirements-cloud*`, boto3, the cloud files in `deploy/`, and the
    M2/EC2/DuckDNS scripts.
  - Renames: `cloud_storage.py` → `recovery_storage.py`, `cloud_metadata.py` → `metadata_backup.py`,
    `restore-m2-metadata.py` → `restore-metadata.py`.
  - One-off scripts: M1-M3 `check-*`/`review-*` scripts, `scripts/checks/frontend/*.sh`, and the hazardous
    `start-m3-preview.py` and `share-worker-build.py`.
  - Run vulture and knip once and confirm every hit with grep.
  - `assert/`: keep one zip in `docs/archive/`. `notes/` moves to `docs/archive/notes/`.
- **4. Duplication — completed.**
  Receipts: `docs/evidence/2026-10-19-phase4/`; backend 282 passed, 4/4 mutants killed.
  Shared CPU files are selected by `backend/runtime_sources.py`; Electron uses `desktop/shared` as a workspace.
  - `backend/monitoring/*` and `backend/study/*` are byte copies of `runtime/src/heteroes/product/*` and `heteroes/study/*`.
    Keep a single source if those modules do not import torch.
  - Repeated backend checks: `dispatchHold` read 7 times, `disabledWorkers` 6, backup policy 3, admin auth 3,
    config.json 3, two different `Strict` classes.
  - Shared Electron code goes to `desktop/shared/`.
- **5. Readability.**
  - The formatting commit gets its id in `.git-blame-ignore-revs`.
  - Split `app.create_app` (531 lines) and `lab.install_lab_routes` into APIRouters.
  - Split `devices.AgentRuntime` (schema/migrations, scheduling, poll).
  - Split the dense TSX pages.
  - Remove unused translation keys.
  - List the security findings (`/health` leaks `privateLabUrl`, `/mnt/sekai` is hard-coded) for the owner; do not change them silently.
- **6. Documentation.**
  - One `README.md`, one `AGENTS.md`, and one `docs/HANDOFF.md` that replaces the chain of session handoffs.
  - Superseded docs move to `docs/archive/`.
  - Update `quickstart-vi.md` to r10.
  - `check-all.sh` also runs the runtime tests and the format/lint checks.

## Commands and gotchas
- Whole check: `scripts/check-all.sh <fresh dir>` (CPU only). Backend: `CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest backend/tests -q`.
  Runtime: `cd runtime && CUDA_VISIBLE_DEVICES='' PYTHONPATH=src ~/miniforge3/envs/heteroes-match/bin/python -m pytest -q`.
- Mutation check: `.venv-backend/bin/python -I scripts/mutation-check.py --repo . --copy backend --copy desktop/worker/resources/reference.json --env CUDA_VISIBLE_DEVICES= --test "<pytest cmd>" --mutants m.json --scratch <dir>`.
  A mutant's `old` text must appear exactly once in its file.
- A shell started from VS Code exports `ELECTRON_RUN_AS_NODE=1`. `check-all.sh` unsets it; any other Electron command needs `env -u ELECTRON_RUN_AS_NODE`.
- Never use `pkill -f <pattern>`: it can match your own shell. Stop processes by PID or by port.
- The Lab Server installer packs every `backend/*.py`, so any backend change changes the next build. That is expected.
- `ruff` is at `~/miniforge3/envs/ai/bin/ruff`.
