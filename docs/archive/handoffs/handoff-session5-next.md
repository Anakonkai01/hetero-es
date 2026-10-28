# Session 5 review handoff — continue here (2026-10-20, Claude)

Read `../AGENTS.md`, then this file. It supersedes the operational state of `handoff-session4-next.md`, whose owner
decisions and authority section still applies unchanged (no new ES algorithm or learning runs; no subagents; tests before
behavior and scratch mutation checks; English code/docs, Vietnamese with the owner; never push/tag/deploy; frozen
`noise/es/ledger/generation_record.py` untouched; SSH/GPU use on this 5070 Ti and both loaned 3060s authorized for the
isolated tests; never use the revoked public identity `3060-thao`; live wipe/deploy/publication are owner-only).

Branch **feat/v3-audit-recovery**, session start `67b4811`, end `8656e3b` plus this handoff commit. Nothing pushed,
tagged, merged, published or deployed. Frozen numerical files are unchanged in this session.

## What was done (commits since 67b4811)

| Commit | Result | Evidence (docs/evidence/) |
| --- | --- | --- |
| 2d86bce | Web shows the one-line Linux/WSL Worker install (landing downloads, Get started, Workers → Add a GPU computer), private-transfer aware: `curl -fsSL '<installer>' \| HETEROES_DOWNLOADS='<same dir>' bash`. Publisher: preflight every link before switching the `install-worker.sh` alias, tolerate a stale `.pending`, drop the alias for app-only/rollback builds. Mutation: publisher+route 6/6, command builder 4/4, file-backed eval identity 2/2 (added a splitSeed provenance case) | 2026-10-20-linux-cli-page |
| cfb07cc, 6e0c596 | Usage: coordinator "GPU seconds" now bills only the synchronized update, not copying/writing/hashing the child weights (was 0.51 s billed for a 0.5 s publication in the test). Mutation 2/2 | 2026-10-20-update-gpu-window |
| 1ec1b18 | First full check found: Lab Server source package lacked `product/cpu_coordinator.py` (packaged server could not start since 66d3fe7); a device test still enforced the retired 11 GB coordinator limit; a browser check used the pre-efe8e33 "Declarative scorer" label | 2026-10-20-session5-checks |
| 1d0b6ba, 317f5cf | r11 candidate3 built/prepared/packaged-checked (superseded) | 2026-10-20-r11-candidate3 |
| 8ed1935 | **Managed Python rewards never started**: `run_supervisor.validate` called `validate_options` without `allow_python`, so the coordinator agent refused every Python-scored COORDINATE (found by the first real `serve --lab`). Now admitted with the frozen `pythonCode` still required. Mutation 3/3 | 2026-10-20-managed-python-coordinator |
| 595faa1 | **Cancel before accept never released**: a run cancelled while its coordinator had not accepted COORDINATE stayed STARTING and kept its devices. Now released only with `cancelRequested`, the lab-created STARTING snapshot and every device confirming stopped processes; without cancel the lab keeps waiting. Mutation 3/3 | 2026-10-20-cancel-before-coordinate |
| e123935 | Full `check-all.sh` **ALL PASS at 595faa1**, run alone (`checks-595faa1`; `checks-8ed1935` was edited mid-run, intermediate only) | 2026-10-20-session5-checks |
| d435c3b, 2b71df3, 481f91a, 8656e3b | **r11 candidate4** built at e123935, resources committed, prepared hashed installers (not published), source-copy + packaged Linux Server + packaged Linux Worker PASS; native Windows upgrade/restart/uninstall | 2026-10-20-r11-candidate4 |
| cf996a2 | **Real managed `serve --lab`**: CPU coordinator = fresh CLI in Thao's WSL (installed with the one-line command), GPU worker = native Windows RTX 3060 desktop Worker (candidate4). Python reward, 2 generations, population 4. COMPLETED. Independent 5070 Ti re-execution from the run's own documents: all 32 texts (+hashes), 8 rewards, both records and both child hashes **exactly equal**. Usage: 256 tokens, 10.515 GPU s (worker), 0 coordinator GPU s, coverage complete; visible in API and browser | 2026-10-20-managed-cpu-coordinator |

Candidate4 artifacts: `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261020-r11-candidate4/` (Archive UUID
10443D1F443D094C), hashes in `2026-10-20-r11-candidate4/installers.sha256` and `installers-prepared.json`.

## Review hotspots

- `backend/agent_scheduling.py::_release_confirmed`: the new unstarted-cancel branch writes a CANCELLED snapshot. Check it
  cannot fire for a coordinator that accepted and is still preparing (it requires a fresh `coordinatorAlive: false`
  report, which an accepting agent does not send) and that completedAt/terminal projection is what the UI expects.
- `run_supervisor.validate` now mirrors `prepare_run`'s Python detection; the worker path never receives code.
- Coordinator agent failures are silent for RuntimeError and only counted for ValueError (`command_failures`); the stuck
  STARTING run showed no reason in the lab. Surfacing `record_failure` reports to the experiment is a worthwhile follow-up.
- `serve --lab` idempotence: a crash between experiment POST and receipt write can create a duplicate draft (documented,
  not fixed). The CLI process exits after completion; the CLI device then shows offline (expected).
- `publish-local-installers.py`: alias switch and manifest replacement are separate atomic renames (window documented).
- Session 4 hotspots not re-reviewed in depth here: usage partial semantics across resume, recovery trust boundaries,
  vLLM probe scope. CPU scheduling, lab-offer idempotence and comparison statistics were reviewed and look correct.

## Live state at the end (all test devices OFF, isolated lab stopped)

- Public lab untouched; `local-lab.py status` shows it alive. Never operate it through the isolated scripts.
- Isolated lab `.scratch/isolated-lab/` (candidate4: `start-c4.sh`, worker `worker5070/start-c4.sh`), stopped by SIGTERM
  to its drivers; ports 8790/8765/8799 closed. Helper `api.py` (cwd there), `.scratch/session5-managed/state.py <run id>`.
- The stuck candidate3 run `ec1c8f27…` was **released** (CANCELLED, devices free) after the owner restarted Quang's
  WSL: `2026-10-20-stuck-run-release`. Quang's WSL works again, but its Windows C: has only **6.9 GB** free (the likely
  cause of the I/O errors). Its CLI home `~/.local/share/heteroes-c3-cpu` now holds candidate4 (CPU self-test passed;
  device `47c8cd14…`); the old GPU CLI home `~/.local/share/heteroes-worker` lost its runtime (reinstall when needed).
- Thao: WSL CLI home `~/.local/share/heteroes-c4-cpu` (13 GB incl. run checkpoints; device `47e0546d…`, approved, offline).
  Windows C: **16.6 GB free** (WSL vhdx grows on C:); D: 838 GB. The Windows test Worker was uninstalled (device
  `106afff2…` remains approved/offline in the isolated lab). Candidate4 installer copy remains in the Windows temp task dir.
- Private copies (ledger/usage/config) of the managed run are in `.scratch/session5-managed/thao-run/`; never commit.
- Disk: system ~27 GB free after deleting superseded test runtimes/check folders (test data, owner-authorized).

## Unfinished / next

1. Free space on Quang's C: before any further WSL install there; optionally repeat a managed run with Quang as GPU worker.
2. Optional: a managed run with audits (two generating workers) and a Linux desktop GPU worker together with Windows.
3. Owner-only r11 flag day (checklist in `handoff-session4-next.md`): review candidate4 hashes/evidence, choose the
   window, back up, wipe only with explicit approval, publish exactly the prepared bytes (`publish-local-installers.py
   --prepared-receipt docs/evidence/2026-10-20-r11-candidate4/installers-prepared.json --receipt <new>`), upgrade lab and
   workers together, smoke test. The builds' default lab is the live lab, so do not pair r11 workers before the switch.

Resume prompt:

> Read AGENTS.md and docs/handoff-session5-next.md, review the session 5 commits, then continue Unfinished in order.
> Preserve the owner's settled decisions. Do not push, tag or deploy.
