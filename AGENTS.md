# AGENTS.md — HeteroES (one repository: runtime, Web/API, apps, lab operations)

Since 2026-10-19 the runtime repository (`hetero-es`) and the product repository (`Hetero-ES-LLM`) are one repository.
The runtime (numerical core, ledger, workers, device agent) lives in `runtime/`; the product (FastAPI backend, web UI,
Electron apps, lab operations) stays at the root. Both histories were kept: every old commit id still resolves, and the
old branches are kept as `archive/runtime/*` and `archive/product/*`.

Read first: **`docs/session-handoff-2026-10-14-windows.md`** (first real Windows Worker, r8-r10, what is not shown), then
`docs/session-handoff-2026-10-13-ui.md`, `docs/session-handoff-2026-10-12-lf1.md` (owner rules and decisions),
`runtime/CLAUDE.md` (numerical contract, module map), `runtime/HETEROES_LLM_STATUS.md` (first block) and
`runtime/docs/adr/ADR-004..007`.

Non-negotiable rules:
- Talk to the owner in Vietnamese, simply, short; documentation and code comments in English.
- Never push or tag. No `Co-Authored-By` or other generated-by trailer in commits. Commit in logical groups on a
  working branch (2026-10-19: `refactor/cleanup`); `main` is what the lab runs.
- Tests first, then a mutation check on a scratch copy (`scripts/mutation-check.py`). Evidence READMEs state what they do NOT show.
- Never print or commit secrets (credentials, tunnel credentials, device tokens, signing keys).
- The lab on this workstation is live and public. It runs from a deployed clone of `main` in
  `~/.local/share/heteroes-lab/app` (see `deploy/heteroes-lab.user.service`), never from this working tree. Change it
  only through `scripts/local-lab.py`, never kill its processes by hand, run GPU work only with `--gpu` and
  `HETEROES_GPU_ACCEPTANCE=1`.
- Recipe v1 numerics (`runtime/src/heteroes/{noise,es,ledger}/`, `generation_record.py`) must not change behaviour
  without a separate owner decision (2026-10-19: automatic formatting is allowed, with an AST-equality proof).

Whole CPU check (fresh evidence directory each time): `scripts/check-all.sh docs/evidence/<date>-<name>/checks`.
Quick checks:
- runtime: `cd runtime && CUDA_VISIBLE_DEVICES='' PYTHONPATH=src /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q`
  (2026-10-19 baseline: 2,115 passed, 100 skipped)
- backend: `CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest backend/tests -q`
- apps: `cd desktop/worker && node --test tests/*.test.cjs`; lab: `python3 -I ~/.local/share/heteroes-lab/app/scripts/local-lab.py status`.
