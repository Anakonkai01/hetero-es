# Second learning experiment on the runtime, 2026-10-08 (written by the AI; the owner has not reviewed it)

Why: the first experiment (`artifacts/experiments/2026-10-07-learning-runtime/`) was mostly decided by the 256-token cut (`2026-10-08-uncut-probe`). This one trains on level-1 arithmetic (two-digit operations, replies of about 96 tokens, base accuracy 64.5 percent
at 256 and at 512 tokens), with 128 training questions, N = 32, a validation set to choose the checkpoint, held-out sets evaluated with room to finish, and a cumulative shuffled-coefficient control. Criteria: `PREREGISTRATION.md` (written before the run; Addendum 1 after).
Runs: **D1** (`runD1/`, id `lrtD1`): 5070 Ti alone, sigma 1e-3, alpha 1.5e-3, 40 generations, 63 minutes. **D2** (`runD2/`, `lrtD2`, EXPLORATORY): from D1's generation 20, sigma 5e-4, alpha 7.5e-4, 20 more generations (`run_coordinator.py --init-weights`).
Analysis: `analysis-runD{1,2}.json/.log`, `randomwalk-runD1-from20.json`, `summary-D.txt` (the tables below come from it), `summarize_v2.py`.
The replay of every generation was checked against the next checkpoint's hash by `analyze_run.py`: see the logs (all `MATCH`).

## Result by the criteria written in advance (run D1)
| criterion | measured | met |
|---|---|---|
| P1: H1 of the checkpoint chosen on V1 (generation 15) at least 6 points above the base | 62.1 -> 84.0 percent (+21.9) | **yes** |
| P2: parent+ beats parent- in at least 60 percent of the non-tied generations (at least 20 of them), sign test p <= 0.05, and the three shuffled walks end below the real run | 22 of 26 non-tied generations (14 ties), p = 0.0003; walks end at 87.5, 77.3, 83.6 against the real 94.5 on the training questions | **yes** |
| P3: training accuracy at least 8 points above the base | 65.6 -> 93.0 (+27.3) | **yes** |
| P4: mean of H2 and H3 over the last three checkpoints not more than 6 points below the base | H2 85.7 against 93.8 (-8.1); H3 64.3 against 81.2 (-16.9) | **no** |

**Label by the rule: "no evidence of improvement on held-out arithmetic in this experiment"** (the last branch of the rule; Addendum 1 explains that it describes D1 badly: the held-out gain on the training family is large and the failure is the damage elsewhere).

## Reading (what is measured and what is my inference)
- **The gain on the trained family is real as a score and it is mostly a change of how the model answers.** H1 rises from 62.1 to 82-85 percent within 5 to 10 generations and stays there (the V1 validation set agrees: 73.4 -> 84.8-87.9); the mean reply length of H1 falls from 247 to about 95 characters.
  `artifacts/experiments/2026-10-08-direct-answer-probe/README.md`: the base model asked for only the final integer already scores 77.0 percent on H1; the D1 checkpoints with the workload's prompt reach 82.4 to 84.0 (+5 to +7 points, borderline, about 2 standard errors) and,
  asked for only the integer, are not better than the base (76.6 and 68.8). So ES taught the model mainly to answer the way the base model was already best at; whether it also learned a little arithmetic cannot be separated in this run.
- **The direction of the update matters** (P2): the real steps beat the anti-steps in 22 of 26 decisive generations, and 20 steps of the same noise with the rewards shuffled leave the training accuracy 7 to 17 points lower than the real run. One run.
- **Collateral damage is large on word problems** (H3 81.2 -> 50 to 77 over the checkpoints, and 15 to 33 percent in D2 after generation 25) and moderate on three-operand expressions (H2 93.8 -> 83.6 to 87.5 from generation 15 on): the trained model answers directly, which the word problems do not allow. Generation 5 already has H3 75.0 and H2 92.2.
- **D2 (exploratory, one run, sigma and alpha changed together):** halving sigma made the 32 candidates as good as their parent (mean reward 93.9 against the parent's 94.4, while with sigma 1e-3 in D1's generations 20-39 it was 89.5 against 93.7: the late "noise worse than the parent" of the first experiment is
  cured), but it did not improve H1 or V1 (82.0 and 86.7 at the end, as in D1) and **H3 fell further** (22.7 against 60.9). It is a negative result for "a smaller sigma helps held-out accuracy" in this setting; it cannot say whether sigma or alpha did it.
- The training accuracy saturates at about 93 to 94 percent from generation ~15; after that H1 does not move (82.0 to 82.4).

## Limits
One model, one hardware, one run per setting (no replication of D1 with other noise: the run-to-run spread is unknown, in the first experiment it was large), 128 training questions, 40 generations, N = 32, one family; the "direct answer" probe uses one wording; H1 and V1 have 256 questions (one question = 0.4 points).
The preregistered sets, thresholds and the selection by V1 are as written; everything in "Reading" about the mechanism is post hoc. Nothing here says anything about other tasks, models, or other algorithms.
