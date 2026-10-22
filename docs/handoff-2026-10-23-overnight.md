# 2026-10-23 overnight (Claude, autonomous): candidate14 closed, candidate15 (GPU engine v2) live, faults, soak

Owner went to sleep ~00:05 and authorized the whole night: auto mode, sudo on all machines, deploy/commit/push/FF.
Owner choices given in chat: do everything (speed, faults, soak, GPU engine v2); borrowed machines usable freely and
restarts allowed; Qwen 0.5B; report = short Vietnamese message + this file; 1660S dropped (dead); **GPU engine v2 is the
system default** (00:55). Evidence and numbers: `docs/evidence/2026-10-23-overnight/README.md`.

## State

- `main` = `feat/overnight-2026-10-23` (pushed). Candidate14 closed first (`df11478`, see
  `handoff-2026-10-22-candidate14-claude-next.md`).
- **Candidate15 installed everywhere**: nhan + nhut CLI runtime `3fd3f301ef0a`, native Windows Desktop runtime
  `0ce7d7013c33`, all APPROVED/ON. Installers published on the live lab (manifest build `lf1-20261023-r11-candidate15`).
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

## Results (details in the evidence README)

- Speed, same declared run: GPU engine 3 machines 149 s wall vs CPU engine 315 s; all six runs (1/2/3 machines × CPU/GPU)
  have the identical weights hash chain.
- Fault run: 80/80, 99/99 audits, network cut / nhut reboot / Windows app kill all recovered; replay equal on nhan (GPU
  noise) and nhut (CPU noise). The worker SIGKILL was repeated in the soak (restarted in 14 s).
- Soak: see the evidence README section 5 (filled in the morning).

## Open / next

- Start-up of a run is ~40 s (base validation ~25 s + workers loading the model ~20 s) and the end ~35 s; it dominates
  short runs. Not changed.
- Windows device does not keep ON after restart (its owner choice); after an app crash someone must switch it ON.
- Old isolated lab on port 8790 (`.scratch/isolated-lab`) is still running from an earlier session; untouched.
- Pre-existing untracked `docs/evidence/2026-10-22-candidate13/deploy-lab-c13c.log`, `monitor.pid`: preserved.
