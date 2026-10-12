# AGENTS.md — HeteroES product repository (Web/API, apps, lab operations)

Any AI agent or engineer starting here: read **`docs/session-handoff-2026-10-12-close.md`** first (public r5, reported Windows blockers, owner-requested stop), then **`docs/session-handoff-2026-10-12-lf1.md`** and **`docs/session-handoff-2026-10-12-codex.md`** for owner rules and the earlier r5 continuation (state of the live lab,
owner rules, decisions, backlog, first ten minutes). Then the ADRs in the runtime repository
(`../hetero-es-m3-runtime/docs/adr/ADR-004..007`) and `docs/evidence/2026-10-12-lf1/README.md`.

Non-negotiable rules (full list in the handoff, section 2):
- Talk to the owner in Vietnamese, simply, short; documentation and code comments in English.
- Never push or tag. No `Co-Authored-By` or other generated-by trailer in commits. Commit on the branch `feat/local-first-lf1` in logical groups.
- Tests first, then a mutation check on a scratch copy (`scripts/mutation-check.py`). Evidence READMEs state what they do NOT show.
- Never print or commit secrets (credentials, tunnel credentials, device tokens, signing keys).
- The lab on this workstation is live and public: change it only through `scripts/local-lab.py`, never kill its processes by hand, run GPU work only with
  `--gpu` and `HETEROES_GPU_ACCEPTANCE=1`.
- Recipe v1 numerics are frozen; they live in the runtime repository, not here.

Quick checks: backend `CUDA_VISIBLE_DEVICES='' ../Hetero-ES-LLM/.venv-backend/bin/python -m pytest backend/tests -q`;
apps `cd desktop/worker && node --test tests/*.test.cjs`; lab `python3 -I scripts/local-lab.py status`.
