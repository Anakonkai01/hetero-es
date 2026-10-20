# Handoff — opened ES update formula, Countdown/GSM8K, Worker data folder (2026-10-19/20)

> **Superseded on 2026-10-20 by the owner:** the learning items below (run 1 test/CommonsenseQA scoring, run 2) are
> parked. The project claims a system, not that ES learns (`../AGENTS.md`, "Project claim"); see the last section of
> [HANDOFF.md](HANDOFF.md).

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

## Later results (2026-10-20)

- Full CPU check at 38eb72b: 22/22 after fixing the Worker onboarding build-name pattern
  (`evidence/2026-10-20-check-all`; runtime 2326 passed / 100 skipped, backend 321).
- r11 **candidate2** built and both packaged Linux checks PASS (`evidence/2026-10-20-r11-candidate2`).
- GSM8K base Qwen2.5-0.5B: 0.525 on 200 validation rows (`evidence/2026-10-20-gsm8k-dataset`).
- Countdown pilot 2 stopped after 2 generations by the owner's choice (GPU to GSM8K). Countdown is postponed.

## Owner direction after reading the papers (2026-10-20)

Focus on GSM8K in the spirit of "Understanding ES for LLM Reasoning" (2608.27351): **basic GSM8K run first**
(one z-score run, greedy evaluation on the held-out test); Pass@K, ablations and GRPO only after learning is
seen. Do check forgetting on **1–2 small other tasks** (CommonsenseQA first). Agentic ESOpt (multi-turn agents) later.

## Next steps, in order (no heavy design left)

1. **Launch and watch GSM8K run 1** (GPU allowed): `.scratch/gsm8k/run1/launch.sh` (detached with
   `setsid nohup ./launch.sh &`; spec: N=32, σ=1e-3, α=5e-4, zscore@1, batch 32, 512 tokens, chunk 64,
   60 generations ≈ 9 min each; data `.scratch/gsm8k/v1` from `runtime/scripts/build_gsm8k_dataset.py`). Two
   aborted starts are kept as `run-aborted-1/2` (nothing to read). Watch `run/events.jsonl`
   (`generation_complete` rewards). Stop only by PID/process group, never `pkill -f`.
2. While it runs: CommonsenseQA builder like the GSM8K one (`tau/commonsense_qa` revision
   `94630fe30dad47192a8546eb75f094926d47e155`, MIT; rows `prompt` with the question and A–E choices,
   `answer` letter; scorer `choice-letter@1` takes A–D only today — add E or a `choice-letter@2`, with tests).
   Add to `runtime/scripts/v3_evaluate_checkpoints.py` an option to score a checkpoint on OTHER rows with another
   declarative scorer (forgetting), with tests and a mutation check.
3. After the run: evaluate generations -1, 19, 39, 59 on validation, choose by validation only, then the chosen and
   the base on the GSM8K test and CommonsenseQA; new evidence folder with "What this does NOT show".
4. Then: Windows candidate2 (installer, D: data folder, self-test, uninstall; owner present), the isolated
   3-machine lab, preregistration and the comparisons.

5. **r11 / later (owner, 2026-10-20):** make the batch sampler pluggable (today hard-wired, `documents.py:135`) and have a
   fresh strong reviewer run the researcher-readiness review in [review-researcher-readiness.md](review-researcher-readiness.md).

**Update (end of 2026-10-20 session):** run 1 was STOPPED by the owner after generation 29 (30 generations). Validation
(500 rows): base 0.562, gen 9 0.544, gen 19 0.556, gen 29 0.556: no improvement
([evidence](evidence/2026-10-20-gsm8k-run1-validation/README.md)). Remaining from step 3: score the GSM8K test and
CommonsenseQA (`.scratch/csqa/v1/test.jsonl`, scorer `choice-letter@1`, via `v3_evaluate_checkpoints.py --rows
--rows-scorer`; note the evaluator uses the run's prompt/decoding, 512 tokens) for gen 29 and the base. Then decide
run 2 with the owner: the references use batch 64, epoch-wise data, 234 steps (see es-literature-local-recipe.md).
GPU is free. Reference papers and code are in `.scratch/literature/`.

Done 2026-10-20: GSM8K run 1 launched (PID-detached, ~6 min/generation); `choice-letter@1` accepts E;
`v3_evaluate_checkpoints.py --rows/--rows-scorer`; `build_commonsense_qa_dataset.py` (data in `.scratch/csqa/v1`);
check-all 22/22. `run1.log` only holds a second, OOM-dead launch; read `run/events.jsonl`.

Known limits: `v3_evaluate_checkpoints.py` replays with the CPU engine only; managed-run validation (`v3/tracker.py`)
still decodes 16 prompts per call regardless of `evaluation.chunk` (coordinator-only, does not affect identity).
