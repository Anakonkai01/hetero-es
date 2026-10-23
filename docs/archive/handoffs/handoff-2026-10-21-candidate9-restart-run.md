# Candidate9: both c8 restart causes fixed (code DONE), build done, device installs and the short restart run left (ops only)

Checkpoint 2026-10-21 ~16:20 +07, branch `feat/r11-scheduling-elastic`, local only (**not pushed**). Supersedes
`handoff-2026-10-21-c8-member-restart-stop.md`. No subagents (owner rule). The code part is finished; what is left is
operations, suitable for a Sonnet session. **Stop rule still applies:** if the run shows a restart failure, stop and
hand off. Do not patch code.

## Done this session (Opus)

- **`f21cc1f` fix, both causes proven from the c8 run's own records** (`evidence/2026-10-21-c8-restart-causes/README.md`):
  1. Windows: the lab refused the startup `PATCH /device/qualification` (409) while the run held the GPU. The app then
     quit the agent and started a new boot every ~10 s, with no log line. The lab audit has no
     `DEVICE_QUALIFICATION_UPDATED` from 14:45 until 15:03:54, which is exactly the run's end. Fix: an identical
     qualification for the current boot is a no-op even while reserved; a refused start is logged once and retried after
     30 s.
  2. 1660S rejoin: after the second JOIN the run's assignment lacked the 1660S. The coordinator's next report still
     listed it as `left`, so `release_left_members` released it again, and every restart probe got 403, which was
     swallowed. Fix: never release a worker the lab counts as a member. The supervisor now logs
     `worker_restart_deferred` with `httpStatus`, once per reason.
  Tests failed before the fix. Backend 394, runtime 2584 (102 skipped) and worker 89 pass. Mutation check: 11/11 killed.
- `0d36dda` CPU gate 23/23 ALL PASS. `10e5a46` run predeclaration: `evidence/2026-10-21-restart-run-candidate9/`. The
  monitor runs one fault at a time (6 tests, 24/24 mutants).
- `2475135` build `lf1-20261021-r11-candidate9` (resources committed). Prepare-only done
  (`evidence/2026-10-21-r11-candidate9/installers-prepared.json`, not published). Source bytes are all equal: Worker 105 files
  (runtime `9a553d2dfae9…`), Server 182. Both Electron bundles contain the `service.cjs` fix. Package checks: source-copy,
  packaged Linux Worker and packaged Linux Server all PASS (`evidence/2026-10-21-r11-candidate9/RESULTS.md`).

## Device state at the checkpoint (uncommitted receipts in `evidence/2026-10-21-candidate9-device-upgrades/`)

| Device | State |
| --- | --- |
| Installer HTTP 8802 | serves the candidate9 directory (log `.scratch/c9-http8802.log`) |
| Isolated lab 8790 | **candidate9 running** (`.scratch/isolated-lab/start-c9.sh`); runtime `37eb126524bb`, 63 files equal source |
| 1660S CLI | c9 installed (`9a553d2dfae9`), src equals repo (tree hash `b8e92142…` 104), GPU self-test PASS. **Agent NOT running** (the machine rebooted at 15:30); start it: `nohup setsid heteroes-worker run` (log under `/tmp/heteroes-r11-c9`) |
| Thao WSL CPU coordinator | c9 installed, src equal, CPU self-test PASS (`--device cpu`). Note: `DISK=/` was used this time |
| 5070 desktop worker | **NOT running.** `worker5070/start-c9.sh` hit the known 30 s Electron cold-launch timeout (`app-c9.log`). Rerun it, then write `{"action":"install"}` and `{"action":"selftest"}` into `worker5070/commands.jsonl` (results in `results.jsonl`) |
| Thao native Windows | still candidate8, app quit. Do as for c8: `install-c8.ps1` → `install-c9.ps1` (installer hash = `installers-prepared.json`, Windows entry), `action.py install`, `action.py selftest`, launch (`launch-c9.ps1`), `verify-install-c9.ps1` (build name + runtime sha `9a553d2d…`) |
| **Quang** | **OFFLINE** since ~15:55 (Tailscale). Ask the owner to wake the machine/WSL. Then run `install-cli.sh` (OLD=`b377c9c94cea`, DISK=/mnt/c), self-test with `LD_LIBRARY_PATH=/usr/lib/wsl/lib`, then start the agent |

All contribution is OFF. Nothing is published or pushed.

## Next, in order (Sonnet)

1. Finish the device receipts above, then write `RESULTS.md` + `SHA256SUMS` in `evidence/2026-10-21-candidate9-device-upgrades/` and commit.
2. Copy the run tools to `.scratch/r11-c9-run/` (`operator/*`, plus `snapshot.py` to Thao `/tmp/heteroes-r11-c9/`
   together with `spec.json`, `rows.json`, `reward.py`, `run-thao.sh`). Turn contribution ON for every current boot,
   offer the run (`run-thao.sh`, token on stdin, `HETEROES_C9_RUNTIME=9a553d2dfae9`), and start
   `operator/monitor.py <experiment>` detached. Everything else is as in the c8 run folder.
3. Verify as declared in `evidence/2026-10-21-restart-run-candidate9/README.md`: verdicts, `verify_managed_run.py`, then
   `verify-records.py` with the declared flags, negative controls, screenshot, `RESULTS.md`.
4. If all three verdicts are `recovered` and parity holds, `plan-r11-release.md` steps 6-8, each irreversible step with
   the owner's "đồng ý". If any verdict is `failed`: STOP and hand off. The `worker_restart_deferred` lines in the
   coordinator `lifecycle.jsonl` now say why.

## Retained, unexplained

- The Electron cold-launch 30 s timeout from the Archive volume (now also hit by the 5070 worker app start).
- Items in `handoff-2026-10-21-c8-member-restart-stop.md` still stand, except the two causes fixed here.
