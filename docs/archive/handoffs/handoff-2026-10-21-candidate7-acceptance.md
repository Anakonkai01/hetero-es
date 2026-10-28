# Candidate7 checked, installed, managed acceptance COMPLETED — next: verification

Checkpoint 2026-10-21 ~13:25 +07, branch `feat/r11-scheduling-elastic`. Everything is committed locally, **nothing is
pushed**. Supersedes `handoff-2026-10-21-scheduling-elastic.md` (steps 1–3 of it are done, except the verification).
No subagents (owner rule).

## Done this session

| Commit  | What                                                                                                                                                                                                                                             |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1837733 | Candidate7 prepare-only; every runtime source byte equals the source (Worker 105 files with `membership.py`, Server 182); source-copy, packaged Linux Worker and Server PASS (`evidence/2026-10-21-r11-candidate7/`)                             |
| 90f4811 | Isolated lab, 5070 desktop, Thao Windows 3060, Thao WSL CPU coordinator and 1660S on candidate7, installed sources equal, all self-tests PASS; 1660S paired + approved as `cli-3e355c6e9e70` (`evidence/2026-10-21-candidate7-device-upgrades/`) |
| e831f3d | Acceptance predeclaration + operator helpers (monitor logic tested, 10/10 mutants killed) (`evidence/2026-10-21-long-multimachine-run-candidate7/`)                                                                                              |
| 0f3f2ae | Run logs: `monitor.jsonl`, `operator-events.jsonl`                                                                                                                                                                                               |

**Owner decisions this session:** delete unneeded files ("có những cái ko cần thiết thì xoá đi"): done, 5070 system disk
11 → 45 GB free (list in the device RESULTS). Quang is offline, so the g20 hard stop targets **Thao's Windows 3060**.

## The managed run `18248941640741ccb6f031d43fbf7ec4`

COMPLETED, 50/50 generations, 400 results: 5070 314, Thao Windows 75, 1660S 11. Audits 9, mismatches 0, no
quarantine. greedy-tail, ~22 s per generation.

- 1660S JOIN requested at g10 (HTTP 200), ledger JOIN effective g11, first result ~g15; LEAVE requested at g30, effective
  g31, confirmed stopped.
- Hard stop at g19 while Thao Windows held `g19/c3` attempt 1: 6 processes stopped (PIDs and start times in
  `operator-events.jsonl`), 0 remaining. One `expiry` row for that worker. Relaunch after 308 s, contribution ON 200.

## Not done (next session, in order)

1. **Verification** (nothing claimed yet). Collect a private, consistent ledger/usage copy from Thao
   `~/.local/share/heteroes-c4-cpu/agent-state/runs/18248941640741ccb6f031d43fbf7ec4/` (adapt
   `.scratch/r11-long-run2/collect.py`; state is COMPLETED, not PAUSED; never commit leases/tokens). Then on the 5070 with
   a separate cache: `verify_managed_run.py`, then `verify-records.py --joiner cli-3e355c6e9e70 --failed-worker
desktop-9f9da13f0f82` (elastic checks already added). Check that `g19/c3` was committed by a later attempt. Run a
   negative control that makes the elastic check fail (e.g. a scratch-copy ledger with a fake non-member result).
   Usage receipt and a browser screenshot (`.scratch/r11-long-run2/browse.mjs`). Write RESULTS.md + SHA256SUMS.
2. **Finding to raise with the owner:** a member that dies and comes back is never restarted. After the relaunch the
   Windows device was ONLINE and ON, but the coordinator kept it `alive: False` and gave it no more work.
   `run_supervisor.py` only starts workers at preparation or on a new JOIN (`_follow_membership`). Not numerical; it
   existed before candidate7. The existing workaround is remove + add (LEAVE releases the GPU when stopped). A fix needs a
   design (restart a confirmed-dead member when it reappears).
3. Quang: still offline; not upgraded (candidate6). Then `plan-r11-release.md` steps 6–8 (Windows uninstall, FF main +
   push, flag day with an "đồng ý" for each irreversible step).

## Current state

- Isolated lab (8790) running candidate7 (`.scratch/isolated-lab/start-c7.sh`, log `server-c7.log`); 5070 desktop
  running (`worker5070/start-c7.sh`, `app-c7.log`); private installer HTTP 8802 running from the candidate7 directory.
- Contribution OFF on all devices. 1660S agent still running (`/tmp/heteroes-r11-c7/agent.pid` there); Thao Windows app
  running after the relaunch; Thao coordinator offer process exited after COMPLETED.
- Windows launch control hangs after the app starts (known); `launch-c7.ps1` and the guarded `driver.cjs` are in
  `.scratch/windows-system-finish/`.

## Retained, unexplained

- First packaged Server check timed out at `electron.launch` (30 s) from the Archive volume; the rerun passed.
- Older items in `handoff-2026-10-21-scheduling-elastic.md` ("Retained, unexplained") still stand.
