# Audit run from the notebook on the lab-only update (2026-10-22 ~19:30)

Lab on `2047452` (web, device names, SDK fix). Run `4eadb5b43c774576bdd62b212b9880cd`, 16 candidates × 10 generations,
5070ti-nhan (coordinator) + 5070ti-nhut (public route only). Notebook `audit-run.ipynb` = `researcher.ipynb` with the
saved lab session and population/generations changed; `executed.ipynb` is its output. `events.json`: worker, audit,
generation and replay events (times in seconds from the first event).

## Result

- COMPLETED 10/10 generations. **Audits ran on this build: 9 selected, 8 completed, all 8 `matched: true`**, in both
  directions (nhan audits nhut's candidates and the reverse). Audit 9 (generation 8) timed out: `audit_incomplete`.
- **FINDING 13 (open, correctness): nhut's worker died after generation 7 and could not come back.** Its replay of the
  8th update (g7 → g8, child `d864a9b6…`) produced `2b9b3f1e…` instead; every restart (6, one per ~70 s, `launch` 1-6)
  replayed 8 updates, failed with the same wrong hash, and exited (`replay_failed`). The first 7 replays were
  `verified: true`. nhan carried generations 8-9 alone (generation 8 took 227 s instead of ~75 s; the pending audit
  needed the second machine). Not known yet: whether the coordinator's chain or nhut's replay is wrong. A ledger
  replay of the child hashes (`verify_managed_run.py`, `--regenerate none`) would tell; not done.
- The restart loop is also a product question: 6 identical restarts of a worker that fails the same way (the limit
  `MAX_LAUNCHES` was not reached; no `worker_restart_limit` event).
