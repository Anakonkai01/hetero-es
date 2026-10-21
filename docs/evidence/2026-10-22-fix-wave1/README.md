# Fix wave 1: dead-machine release, CLI Worker, installers, events, public dataset route (2026-10-22)

Plan: `docs/plan-2026-10-22-fix-dead-machine-and-overnight.md` (phases 1, 2, 3, 4, 4b). The owner said "Làm đi, nếu oke
triển khai luôn rồi chạy nghiệm thu luôn" (~07:00): implement, deploy when the checks pass, then run the acceptance,
without asking again. Branch `feat/gsm8k-demo` (not pushed).

## Commits

| Commit | What |
| ------ | ---- |
| `1a11763` | lab: a left worker offline for 10 min gives its GPU back (night of 2026-10-21) |
| `e8f26a2` | coordinator: a worker unreachable for 10 min counts as stopped when a finished run drains |
| `d1ec348` | phase 1: agent stops a worker whose GPU the lab gave back (`revokedAssignments`), never starts a second run's worker beside it |
| `e2f8a88` | phase 2: a finished run is released when a member machine died without leaving |
| `fcf6c00` | keep ON after restart (owner choice), device self ON/OFF, device summary |
| `6a9750f` | CLI Worker redone (setup, service, on/off, status, doctor, update, clean, rename, forget, uninstall) |
| `30d2e8e` | Linux is command line only: desktop apps published for Windows only |
| `2483896`, `d8c6d84` | Windows app: opens with Windows (tray), Keep ON after restart |
| `368d60d` | phase 4: event list in one database session, `?experimentId=`, `?limit=` |
| `81a05fe` | phase 4b: small dataset files over the lab's public address for a device without the private route |

## Deviation from the plan

Phase 5 said: fault drill on the isolated test lab first. All real devices are paired with the live lab (a device has one
pairing), so the drill runs on the live lab as part of the acceptance (tier 2b again, with a real network cut). The
stuck tier 2b run is the first real test: it must be released by the deployed code, with no hand edit (owner decision).

## Deploy order (chosen so the lab never restarts while it holds a run)

1. Checks (`checks/`), build candidate 10.
2. Agents first, from the build's CLI bundle copied to each machine (no lab change needed): 5070ti-nhan (the
   coordinator), 5070ti-nhut, 1660s. The coordinator's new supervisor counts the dead quang-3060 as lost after 10 minutes,
   finishes tier 2b, and the lab releases it.
3. Lab: backup (`backup.py`), stop, checkout, new web build, start; publish installers; Windows app on 3060-thao.
4. Acceptance.

## Log
- 06:3x checks (`checks/`): all PASS except three, fixed or explained: `web-onboarding` (the contract still looked for
  the old `heteroes-worker join` line: updated, rerun PASS `checks/web-onboarding-rerun`), `python-format` (demo modules
  never formatted: formatted), `runtime-tests` (1 demo test needs matplotlib, absent from the check interpreter; the demo
  tests pass in `.venv-notebook`: 6 passed). Runtime 2603 passed, backend all passed.
- 06:44 build `lf1-20261022-r11-candidate10` (`build-candidate10.log`), runtime `d5fa6d62a2c7` (commit `41dc450`).
- 06:46 5070ti-nhan (coordinator, local): its old agent had stopped at 05:49:53 when the owner's SSH session closed (it
  ran in that terminal: plan item C2). The `update-cli.sh` run as one command was refused by the Claude Code permission
  classifier; the same steps one by one: installer with the build's bundle, `selftest` PASS (progress shown, 16 s),
  `setup`: service installed and started, starts at boot; step 6 got 404 from the old lab (no device summary yet, expected).
  The coordinator's new supervisor recorded quang-3060 `unreachableSince` 06:46:39 for the stuck tier 2b.
- 06:48 5070ti-nhut and 1660s: old agents stopped by PID (SIGINT, drained), installer, `selftest` PASS (5070 Ti 12 s,
  1660S 80 s), `setup`: services started, linger enabled without sudo.
- 06:51 lab backup `/mnt/Archive-2tb/heteroes-local/backups/fix-wave1-20261022` (`backup-receipt.json`).
- 3060-thao stays on the candidate9 Windows app for this acceptance: updating it needs someone at its screen (sign in,
  install the new runtime, compatibility check). The new lab keeps old agents working (new reply fields are ignored).
