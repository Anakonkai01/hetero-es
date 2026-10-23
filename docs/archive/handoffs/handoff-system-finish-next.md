# System finish — next session (written 2026-10-20 afternoon, after session 2)

Read `../AGENTS.md`, then this file, then `handoff-system-finish-codex.md` (details of the Windows backup/restore and the
isolated apps) and `handoff-system-finish.md` (original plan). Branch `feat/v3-audit-recovery`, head `200203d`, working
tree clean, nothing pushed/tagged/deployed. The live r10 lab is untouched (`local-lab.py status`: all three services alive).

Owner instruction for the session that wrote this: do operational work, stop before complex logic/code. **Everything
below under "Open work" was deliberately left for a stronger model.** Talk to the owner in Vietnamese, simply.

## State at the end of session 2

| Item | State |
| --- | --- |
| CPU gate | Full `scripts/check-all.sh` ALL PASS at `580f23d`; receipts `docs/evidence/2026-10-20-system-finish/checks-model-qualification-final/`. Later commits are docs only |
| One-machine baseline `9e68c65d…` | COMPLETED, evidence `baseline-generations.json`, `baseline-final.json` |
| Two-machine run `6590307f…` | COMPLETED; equals the baseline per generation, final weights `670ac40c…` and export; 5/5 audits; `two-machine-final.json` |
| Failed first attempt `302ceac1…` | Kept separately (failed before spawning the Windows Worker); do not merge into the acceptance |
| Isolated lab (port 8790), Linux Worker | **Stopped** cleanly (contribution OFF, app quit, drivers SIGTERM). GPU free. State kept in `.scratch/isolated-lab/` |
| Windows (Thao, native) | Isolated TEST Worker + fresh data still installed; original Worker backed up. NOT restored. See the restore section in `handoff-system-finish-codex.md` |
| Model qualification (`368085a`) | Implemented and CPU/browser tested; never run on a packaged GPU Worker. Build not started |

## Restarting the isolated lab (what worked)

Server: `cd .scratch/isolated-lab && setsid nohup bash start-seed.sh > server-seed.log 2>&1 < /dev/null &` (about 25 s until
port 8790 listens; the DB keeps experiments and devices). Linux Worker: `cd worker5070 && setsid nohup bash start-fix1.sh ...`,
then append to `commands.jsonl` one action at a time, waiting for `results.jsonl`: `{"action":"login","login":"researcher"}`
and `{"action":"contribution","args":{"enabled":true}}`. A run left in DRAINING resumed and completed this way.
Stop in reverse: contribution false, `quit`, verify the app process is gone, then SIGTERM the exact driver PIDs after
checking `/proc/<pid>/cwd`. Do not use `pkill -f` (it matches your own shell). API helper: `.scratch/isolated-lab/api.py`
(run from its directory; never print login replies). Workspace `bcbece5a24834ac28e358fc49db1343f`.
Evidence helper for comparing a run to the baseline: `.scratch/record-two-machine.py` (writes with `open('x')`, so give it a new
output name; run with `PYTHONPATH=runtime/src` and the `heteroes-match` Python).

## Machines (owner authorized in chat on 2026-10-20; sudo password is in AI memory, never in the repo)

- 5070 Ti (this box): coordinator, GPU free.
- 3060 #1 `thao_nguyen@100.92.20.58` and 3060 #2 `quang@100.99.227.8`: both SSH into WSL Ubuntu, RTX 3060 12 GB, driver 617.42.
  Key login works. Windows-installer tests are explicitly LATER; use the WSL side first. These are loans and may disappear.
- WSL has no `node`/`xvfb`, so the Electron Worker does not run there. `~/heteroes-venv/bin/python -c "import torch"`
  **segfaults unless `LD_LIBRARY_PATH=/usr/lib/wsl/lib`** (use the Windows driver libraries, never apt NVIDIA packages).
  Headless route not yet tried: `python -m heteroes.product.agent enroll|run --config <json>` (pairing code, `serverUrl`,
  `computeUrl`, `modelPath`, `workerId`, `stateDirectory`). It needs the worker runtime on the WSL and a lab reachable over
  Tailscale (the isolated lab binds `100.110.165.40:8790`).
- Do not install anything NVIDIA in either WSL; WSL stops when idle; Windows must not sleep.

## Open work (for a stronger model), in resume order

1. **Provenance bug.** `runtime/src/heteroes/runtime_info.py`: `REPO_ROOT = parents[2]`; `git rev-parse HEAD` walks to any
   enclosing checkout, so the packaged run under `.scratch/` reported the root branch. Write a failing regression first
   (packaged copy inside a temp git repo must report `None`, a tracked source checkout must still report its commit).
   One idea: accept git info only if `runtime_info.py` is tracked (`git ls-files --error-unmatch`). Check consumers
   `product/runner.py` (lines ~142/250/283), `qualification*.py`, `selftest.py`; do not rewrite existing recorded observations.
2. **Qualification on real GPUs.** Build the packaged apps from `368085a` or later in a clean detached worktree
   (`.scratch/model-probe-source`, npm ci done) into a fresh directory (Archive UUID `10443D1F443D094C` has ~260 GB; the
   system disk has ~26 GB, so check before builds). Upgrade the isolated apps only while drained. Prove new-model qualification
   on a genuinely different, safe, pinned model on both 3060s and the 5070 Ti, using `heteroes manifest`. CPU/web fixtures are
   not that proof. Requires GPU authorization: explicit `--gpu` and `HETEROES_GPU_ACCEPTANCE=1`.
3. **Original steps 5–8:** Python rewards on web/coordinator subprocess; 1 GB / 10 million-row file-backed datasets and admin
   limits; any machine as coordinator (including native Windows with a pinned adapter); `hf_compact` v3; isolated vLLM probe;
   eval/compare/serve/worker CLI; prompt format, boxed scorer, cost accounting; UI friction 12; final candidate3 package;
   flag-day checklist. Owner decisions are in AI memory (`hetero-es-researcher-product-decisions-2026-10-20`) and the plan
   `~/.claude/plans/h-y-ti-p-nh-n-ti-p-encapsulated-adleman.md`. Do not reopen them.
4. **Windows.** After the installer tests: drain/quit the test Worker, uninstall its test installation, run `restore.ps1`
   (details in `handoff-system-finish-codex.md`), verify credential hashes without launching the original app, then remove the
   private copied login. Never enable the original revoked `3060-thao` identity.
5. Owner-only: the r11 flag-day decision, push, tag, deploy. Do not do these.

## Rules that bit before

- No `Co-Authored-By`/generated-by trailers in this repo. Never push or tag.
- Existing evidence and `runtime/artifacts/` are immutable; new evidence goes in a dated folder with **What this does NOT show**.
- Frozen numerical files (`noise`, `es`, `ledger`, `generation_record.py`) only change with strict AST proof or owner approval.
- Do not claim GPU/Windows/learning acceptance from CPU or fixture checks; the project claim is the system, not "ES learns".
- Run `scripts/check-all.sh` alone (it uses ports 18090-18095 and a shared defaults file); do not build or edit root sources while it runs.

Resume prompt: "Đọc AGENTS.md và docs/handoff-system-finish-next.md rồi tiếp tục theo Open work."
