# AGENTS.md — HeteroES runtime repository (numerical core, ledger, workers, device agent)

Start with **`../Hetero-ES-LLM-m3/docs/session-handoff-2026-10-12-close.md`** (latest public r5 state, Windows blockers, owner-requested stop), then **`../Hetero-ES-LLM-m3/docs/session-handoff-2026-10-12-lf1.md`** (owner rules and decisions), then
`CLAUDE.md` in this repository for the numerical contract, module map and test commands, then
`HETEROES_LLM_STATUS.md` (first block = latest state) and `docs/adr/`.

Where `CLAUDE.md` says every edit and commit needs prior approval and that the owner pushes, later owner instructions
(2026-10-09, 2026-10-12) apply: the AI may commit on its working branch (`feat/local-first-lf1`) in logical groups; it never pushes
or tags; no `Co-Authored-By` or other generated-by trailer; talk to the owner in Vietnamese, simply.

Do not touch Recipe v1 numerics (`noise/`, `es/`, `generation_record.py`, `ledger/`) without a separate decision from the owner.
Tests: `CUDA_VISIBLE_DEVICES='' PYTHONPATH=src /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q`
(latest CPU continuation: 2,115 passed, 100 skipped on 2026-10-12). Mutation check: `../Hetero-ES-LLM-m3/scripts/mutation-check.py`.
