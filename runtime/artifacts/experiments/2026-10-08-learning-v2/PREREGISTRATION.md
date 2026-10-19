# Second learning experiment on the runtime — criteria written BEFORE the main run (2026-10-08, morning)

Written by the AI, after the owner asked for "a bigger training set, a bigger population, a shrinking sigma" to clarify the learning evidence. The owner has not seen this file yet.
Branch `feat/replay-and-learning-v2`.

## Why a new design (what the first experiment taught)
`artifacts/experiments/2026-10-08-uncut-probe/README.md`: the base model scores **81.2 percent on the level-3 held-out set when it may write 512 tokens** (32.8 percent at 256). The first
experiment's gain on that family was mostly "finish before the 256-token cut" (against the 512 baseline: run A +6 points, run B -12, run C +1). The training set had 64 questions (overfitting in run B),
N = 24 was below the 32 that the *Understanding ES* paper found enough for a 0.5B model, and sigma 1e-3 made the 24 copies worse than the parent late in the runs (0.83 against 0.93).
This experiment removes the cut (the training family is **level 1, two-digit operations**: replies of about 96 tokens, base accuracy 64.5 percent at both 256 and 512 tokens), uses 128 training
questions, N = 32, and tests the effect of a smaller sigma.

## What I had seen before writing this (so the reader can discount it)
Measured on the 5070 Ti before this file (scratch scripts): base model, 256 level-1 questions (generator seed 20261007): 64.5 % at 256 and at 512 tokens, 77 % of replies with an `Answer:` line, 96 tokens on
average; level 2: 94 %; level 3: 27 % at 256 tokens and 83 % at 512. The first generation of a smoke run (N = 32) had candidates at 0.709 on average (min 0.45, max 0.86), 232 s per generation on the 5070 Ti alone.

## Setup (fixed now)
- Runtime: `run_learning.py` of this folder, 5070 Ti alone (condition B0x2: two worker processes; the 1660S went down twice in the first experiment), CUDA noise engine, workload `cot_l1_q128`
  (the 128 questions of `make_questions(128, 1)`), chunk 128, FP32 evaluation, N = 32 candidates, sigma = 1e-3, **alpha = 1.5e-3** (the update has a root-mean-square step of alpha / sqrt(N) = 2.7e-4 per weight:
  between run A's 2.0e-4 and 3.5e-4, the value that worked in the 06/10 pilot), **40 generations**, experiment id `lrtD1` (run D1).
- **Run D2 (the sigma test, EXPLORATORY, no verdict):** from the weights of D1 after generation 20 (a checkpoint of D1, `--init-weights`), 20 more generations with **sigma = 5e-4 and alpha = 7.5e-4** (alpha = sigma / 2 as in
  *ES at Scale*; the step is 1.3e-4 per weight), experiment id `lrtD2`. D1's generations 20-39 are the control (same start, sigma 1e-3). The two changes (sigma and alpha) are made together: the test cannot say which one matters.
- Sets (`learnlib2.py`; none contains a training question or a question of another set): **H1** = 256 new level-1 questions (generator seed 20261008, the training family), **V1** = 256 other level-1
  questions (seed 20261009, the VALIDATION set: it only chooses the checkpoint), **H2** = 128 level-2 questions, **H3** = 128 level-3 questions. Held-out sets are evaluated with a limit of 512 new tokens (so that no set is limited by the cut); the training
  questions as the workload does (256).
- Checkpoints every 5th generation (and the base and the last). Offline analysis (`analyze_run.py`): every parent is rebuilt from the ledger's records and checked against the next checkpoint's hash; per generation the
  parent, parent+ (the real step) and parent- (the same step with -alpha) on the training questions; every 5th generation also the shuffled-coefficient control on train and H1; every checkpoint on train, H1, V1, H2, H3.
  **Cumulative control** (`random_walk_control.py`): from the checkpoint of generation 20, 20 steps with the recorded updates' coefficients shuffled, three independent shufflings.

## Criteria (fixed now; judged on run D1)
The **selected checkpoint** is the one with the best accuracy on V1 among the checkpoints after the base (the earliest on a tie). Base = generation 0 of D1.
- **P1 (held-out improvement, the training family):** H1 accuracy of the selected checkpoint is at least **6 points** above the base's H1 accuracy (256 questions: the standard error of the difference of two accuracies on the same questions is about 3 points).
- **P2 (the direction matters):** among the generations whose training accuracy is not a tie between parent+ and parent-, at least 20 generations, parent+ beats parent- in at least 60 percent of them **and** a one-sided sign test p <= 0.05;
  **and** each of the three shuffled walks ends with a training accuracy below the real trajectory's training accuracy at the same generation (40).
- **P3 (training progress):** training accuracy (128 questions) of the selected checkpoint is at least 8 points above the base's.
- **P4 (no damage elsewhere):** the mean over the last three checkpoints of H2 and of H3 is, for each, not more than 6 points below the base's.
- Verdicts. P1 and P2 and P3 and P4 -> "ES improved held-out accuracy on this workload (not limited by the token cut)". P1, P3 and P4 without P2 -> "held-out accuracy improved but the direction of the update was
  not shown to matter". Anything else -> "no evidence of improvement on held-out arithmetic in this experiment" (NOT "ES does not work"). The thresholds are in `learnlib2.verdict`, tested.
- Reported whatever the result: answer-line rate and reply length per checkpoint; the mean reward of the candidates against the parent's accuracy; the run-to-run spread is NOT measured (one run: a replication would be run B-like with another experiment id).

## Stop rules and limits (stated in advance)
- Stop early only for NaN/Inf, an unrecoverable failure of the supervisor (3 restarts of the coordinator, 5 of a worker). No change of criteria after seeing a result: a change goes in a dated addendum.
- One run, one model (Qwen2.5-0.5B), one hardware (the 5070 Ti), one family (two-digit operations), 40 generations, 128 training questions, N = 32. H1 and V1 have 256 questions (one question = 0.4 points); H2 and H3 128.
- P1 uses a validation set to choose among at most 9 checkpoints; the choice cannot leak H1 into the selection, but the selected checkpoint is still the best of several on V1 (a small optimistic bias on V1, none on H1).
- sigma and alpha were not tuned for this task; D2 changes both. A positive result is for THIS setting only.

## Addendum 1 (written 2026-10-08 11:25, after the analysis of D1 and D2): the label, not the criteria
The criteria P1 to P4 are unchanged and were applied as written (`summary-D.txt`). One fact about the rule: the label for "P1, P2, P3 true but P4 false" does not exist in `learnlib2.verdict`: it falls to the last
label, "no evidence of improvement on held-out arithmetic in this experiment", which describes run D1 badly (H1 improved by 22 points; the damage is on the other families). The report quotes the four criteria one by one and
this label only as what the rule printed. Also written after seeing D1 (so POST HOC): `artifacts/experiments/2026-10-08-direct-answer-probe/` (the base model asked for only the final integer scores 77.0 percent on H1).
