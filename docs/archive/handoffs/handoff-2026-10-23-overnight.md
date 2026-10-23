# 2026-10-23 overnight (Claude, autonomous): candidate14 closed, candidate15 (GPU engine v2) live, faults, soak

Owner went to sleep ~00:05 and authorized the whole night: auto mode, sudo on all machines, deploy/commit/push/FF.
Owner choices given in chat: do everything (speed, faults, soak, GPU engine v2); borrowed machines usable freely and
restarts allowed; Qwen 0.5B; report = short Vietnamese message + this file; 1660S dropped (dead); **GPU engine v2 is the
system default** (00:55). Evidence and numbers: `docs/evidence/2026-10-23-overnight/README.md`.

## State

- `main` = `feat/overnight-2026-10-23` (pushed). Candidate14 closed first (`df11478`, see
  `handoff-2026-10-22-candidate14-claude-next.md`).
- **Candidate16 installed everywhere** (07:1x): nhan + nhut CLI runtime `a1c686050d9e`, native Windows Desktop runtime
  `c7d751ce8b3a`, all APPROVED/ON, Windows relaunched normally (no debug ports). Installers published on the live lab
  (manifest build `lf1-20261023-r11-candidate16`). Candidate15 (`3fd3f301ef0a`) ran the fault run and the soak.
- The live lab server code is still `f70b05f` (no backend change since); its served notebook SDK wheel is candidate14's.
  Deploy only if the SDK wheel should carry the GPU path for notebook-local runs.
- Session token renewed at 00:05 (valid ~12 h, `~/.config/heteroes-demo/session.json`; backup `.bak-20261023`).

## What changed in code

1. `b66496e` lost START resend (`product/run_supervisor.py`): a start whose outcome is unknown is sent again with the
   same launch; the lab dedupes. Found when the edge timed out at ~00:07 and a run stayed STARTING.
2. `d1912f3` engine v2 made on the GPU (`noise/engine_v2_cuda.py`, used by `es/perturb.py` and `es/update.py`): same
   bits as the CPU engine, NVRTC via `torch.cuda.jiterator` (works on native Windows), self-test per device,
   `HETEROES_NOISE_DEVICE=cpu` to force CPU. Numerical contract §18.1. Owner-approved change inside `es/`/`noise/`; v1
   untouched (golden tests pass).
3. `1809f08` base validation on a background thread during worker preparation (`product/runner.py`, joined before the
   first generation). `e4a71d0` `pause_check`: pause at the boundary when free disk < 3 × model size + 1 GiB.
4. Packaging: `004da17` candidate15, `9318af4` candidate16. Full runtime suite 2674 passed after the runner changes.

## Results (details in the evidence README)

- Speed, same declared run: GPU engine 3 machines 149 s wall vs CPU engine 315 s; all six runs (1/2/3 machines × CPU/GPU)
  have the identical weights hash chain.
- Fault run: 80/80, 99/99 audits, network cut / nhut reboot / Windows app kill all recovered; replay equal on nhan (GPU
  noise) and nhut (CPU noise). The worker SIGKILL was repeated in the soak (restarted in 14 s).
- Soak attempt 1 failed at generation 60: nhan's disk was full (finished runs keep ~5.6 GB each locally). Space freed by
  deleting own fixtures and moving tonight's eight finished runs' coordinator data to the Archive disk with symlinks
  (`/mnt/Archive-2tb/heteroes-local/overnight-2026-10-23-coordinators/`). Fix `e4a71d0`: pause on low disk.
- Soak attempt 2: **600/600 generations in 4 h, 720 audits matched, replay ALL EQUAL on nhan and nhut**; survived an
  unplanned systemd-oomd kill of the whole service on nhan (02:50) through agent restart + coordinator recovery.
- `1809f08` (startup overlap) gains ~0.5 s here, not ~20 s as its message says; see README section 6.

## Open / next

- Owner decisions needed: (1) a retention rule for finished runs' local coordinator data (~5.6 GB per run on the
  coordinator, never removed); (2) whether to protect the worker service from systemd-oomd (e.g. a unit memory policy) or
  reduce page-cache pressure from per-generation recovery points; (3) whether to move tonight's archived run data back.
- Scheduling: with two fast 5070 Ti the 3060 gets few candidates (410 of 14,400 attempts in the soak); per generation
  only ~3 s is model compute, the rest is update replay, waiting for the slowest member, audits and recovery points.
- Start-up is dominated by workers loading the model (~20 s); the end of a run ~35 s.
- Windows device does not keep ON after restart (its owner choice); after an app crash someone must switch it ON.
- Old isolated lab on port 8790 (`.scratch/isolated-lab`) is still running from an earlier session; untouched.
- The previous session's untracked `docs/evidence/2026-10-22-candidate13/deploy-lab-c13c.log` (15-line deploy receipt, no
  secrets) was committed by a broad `git add docs` in `ef2d0ec`; `monitor.pid` (stale) left untouched.
