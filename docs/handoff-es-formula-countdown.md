# Handoff — opened ES update formula, Countdown/GSM8K, Worker data folder (2026-10-19/20)

Continues [handoff-r11-candidate.md](handoff-r11-candidate.md). Branch **feat/v3-audit-recovery**; nothing pushed,
merged, published or deployed; no lab/device state changed (`3060-thao` REVOKED on the live lab, which runs r10).
Plan approved by the owner: `~/.claude/plans/c-agents-md-v-jaunty-quasar.md`.

## Owner decisions (2026-10-19 night)

Demo first (~1 month), then product, then research. Open the update formula θ ← θ + α_t·Σ_a β^a·(1/n)Σ cᵢεᵢ:
named coefficient rules, a researcher's Python rule (self-hosted only), alpha schedules, momentum via seeds — no Adam.
Editing protected `generation_record.py` approved for this, into r11 (other protected files untouched). Tasks
Countdown (the paper's HF dataset, its 0.1/1.0 reward) and GSM8K; batch 64; GPU free to use; distributed runs on
5070 Ti + 3060 + 1660S later, "when everything is OK"; Windows runtime on another drive instead of cleaning C:.
After pilot 1 the owner chose to keep the paper's reward and run long rather than add partial credit.

## Done (each with evidence and mutation receipts)

| Commit | What | Evidence |
| --- | --- | --- |
| 685c4f7 | packaged Lab Server check rerun PASS (language-independent selector) | `evidence/2026-10-19-r11-server-check` |
| 46aa9ed | `countdown@1` scorer, pinned Countdown builder, scorer column checks | `evidence/2026-10-19-countdown-scorer` |
| 393f366 | optional `evaluation.chunk` (64: 1.8× faster, same texts on one GPU) | `evidence/2026-10-19-v3-eval-chunk` |
| af4673d | centered-rank / python rules, alpha schedules, self-contained momentum records | `evidence/2026-10-19-v3-update-rules` |
| b58668e | the same options in backend, managed runs and the web form | same folder |
| 0014b77 | pilot 1: learns the format, not the task, in 30 generations | `evidence/2026-10-20-countdown-pilot1` |
| 3f6215a | pinned GSM8K builder (official test held out), pre-split local data | `evidence/2026-10-20-gsm8k-dataset` |
| 38eb72b | Worker data folder on another drive, guarded uninstall | `evidence/2026-10-20-worker-data-folder` |
| 1720b7e | checkpoint evaluation by verified replay | `evidence/2026-10-20-evaluate-checkpoints` |

## Running / open, in order

1. **Pilot 2** (`.scratch/countdown/pilot2`, same as pilot 1 but batch 64, 300 generations, one 5070 Ti) started
   2026-10-20 ~05:10. Read it with `runtime/scripts/v3_evaluate_checkpoints.py` on the validation split (base, then
   every ~50 generations) and record a new evidence folder. It is exploratory, not the preregistered experiment.
2. Full `check-all` started at 38eb72b → `docs/evidence/2026-10-20-check-all/checks`; record its result.
3. Build r11 **candidate2** installers (`scripts/build-apps.sh`, new BUILD name) with these changes; Windows 3060:
   install with the data folder on D:, v3 self-test, restart, stop, uninstall (owner present for the GUI steps).
4. Isolated r11 lab on the 5070 Ti (own port/DB; never the live lab or `local-lab.py`) with workers 5070 Ti, 3060
   (Windows), 1660S (qualify first); short runs of each rule; audits, a 1660S drop, replay.
5. Preregistration, then the main Countdown comparison (zscore vs centered-rank vs momentum) and one GSM8K cell;
   HF export reload; preset "Countdown (verified)" on the web; quickstart/report updates.

Known limits: `v3_evaluate_checkpoints.py` replays with the CPU engine only; managed-run validation (`v3/tracker.py`)
still decodes 16 prompts per call regardless of `evaluation.chunk` (coordinator-only, does not affect identity).
