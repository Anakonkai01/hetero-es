# Learning experiment on the distributed runtime, 2026-10-07/08 (night)

**Written by the AI while the owner slept; the owner has not reviewed any of it.** Branch `feat/learning-experiment` (from `feat/audit-hardening-g6`), nothing pushed.
The criteria were written BEFORE the main runs: `PREREGISTRATION.md` (and its Addendum 1, written after run A was analysed and before run C).

## What was asked and what was done
Question: does ES, run through the whole runtime (coordinator + pull workers, CUDA noise engine, FP32 evaluation, tail-aware dispatch), raise the accuracy of Qwen2.5-0.5B-Instruct on
questions it never trained on, and is the gain due to the DIRECTION of the update?

- **Run A** (`runA/`, id `lrtA`): N = 24, sigma 1e-3, alpha 1e-3, 100 generations, workload `cot_l3_q64` (64 word problems, up to 256 tokens of reasoning), chunk 64, policy B4, three
  worker processes (two on the 5070 Ti, one on the 1660S). 2.6 hours. **Run B** (`runB/`, id `lrtB`): the same with other noise (other experiment id), the replication. 3.0 hours.
- **Run C** (`runC/`, id `lrtC`): EXPLORATORY, alpha 5e-4, 60 generations, 5070 Ti only (see its section).
- **Offline analysis** (`analyze_run.py`, outputs `analysis-run?.json/.txt/.log`): rebuilds every parent from the stored checkpoints and the ledger's update records and checks
  the result against the next checkpoint's hash (**all 20 segments of A and all 20 of B matched**: the stored records reproduce the weights exactly), and measures, for every generation, the parent, parent+ (the real step),
  parent- (the same step with -alpha: the CONTROL) on the 64 training questions; every 10th generation also the shuffled-coefficient control and three held-out sets of 128 questions
  (H3 = new questions of the training family; H1 and H2 = other families, two-digit operations and three-operand expressions); every 5th generation all sets (checkpoints).
- **Exploratory random-walk control** (`random_walk_control.py`, `randomwalk-run?-from50.*`): from checkpoint 50, 50 steps with the coefficients shuffled.

## Result in one paragraph
By the rules written in advance **both runs end with the verdict "no evidence of learning in this experiment"**: S1 (new questions of the same family improve by at least 8 of 128) is true and S3 (training accuracy +0.10)
is true in both, but **S2 (the real step beats the anti-step in at least 70 of 100 generations) is false** (44 and 46) and **S4 (no damage on the other families: at most 8 questions lower) is false** (H2 fell by 17 and 28 questions).
That verdict is what the rule gives and it stands. It is not the whole picture, which is in the sections below: the model did improve a lot on the training family (H3 42 -> 112 and 42 -> 89 of 128;
training questions 19 -> 60 of 64), the real updates are far better than random steps of the same size when summed over many generations, and the criterion S2 is badly suited to a model whose training score saturates.

## Numbers
Accuracy in questions correct (base model, then generation 100). Base model: train 19/64, H3 42/128, H1 77/128, H2 116/128. All from `analysis-runA.txt` / `analysis-runB.txt`.

| | train (64) | H3, same family (128) | H1 (128) | H2 (128) | best H3 on a checkpoint |
|---|---|---|---|---|---|
| base | 19 | 42 | 77 | 116 | |
| run A, gen 100 | 60 | 112 | 97 | 99 | 116 (gen 60) |
| run B, gen 100 | 60 | 89 | 77 | 88 | 108 (gen 20) |

Criteria (PREREGISTRATION.md; one question of 128 is 0.78 points, a standard error of about 4 points):

| | S1 H3 +8 | S2 direction (>= 70/100 and mean > 0) | S3 train +0.10 | S4 H1, H2 not lower by > 8 | S5 accuracy among replies with a line |
|---|---|---|---|---|---|
| A | true (+70) | **false**: + better in 44, worse in 22, ties 34; mean +0.0061 | true (+41) | **false**: H1 +20, H2 -17 | true |
| B | true (+47) | **false**: + better in 46, worse in 25, ties 29; mean +0.0091 | true (+41) | **false**: H1 0, H2 -28 | undefined (no reply has an answer line) |

Verdict of both: "no evidence of learning in this experiment" (by the rule). Replicated in the sense of the preregistration (the same verdict class), though the two runs differ a lot in the details (B's H3 peaks at generation 20 and then falls).

### Things that the numbers say that the criteria did not ask (all read from the analysis files)
1. **The training score saturates by generation ~30 (59 to 62 of 64) and from then on a third of the generations are ties** between the real step and the anti-step (A: 30 ties in generations 30-99, B: 25). S2 as written cannot reach 70 of 100 in that situation.
   Counting only the generations that are not ties, the real step is better than the anti-step in 44 of 66 (A) and 46 of 71 (B) (one-sided sign test p = 0.005 and 0.009). This is NOT the preregistered test.
   POST HOC split by phase (positive / negative / tie): A: generations 0-9 3/6/1 (mean difference -0.044), 10-29 15/2/3 (+0.032), 30-99 26/14/30 (+0.006); B: 0-9 5/3/2 (+0.022), 10-29 14/4/2 (+0.022), 30-99 27/18/25 (+0.004).
   In words: in the first ten generations the model is in a chaotic region (the base model is far from the candidates around it, see the next point) and the real step is no better than the anti-step; from generation 10 to 30, while the model is still learning,
   the real step is clearly better; later the step is too small a change on a saturated score for 64 questions to show it.
2. **Why the base model scores 0.30 and every perturbed copy ~0.72 (measured before the runs, scratch scripts):** 36 of the 64 base replies are cut at the 256-token limit with no `Answer:` line; any perturbation at sigma 1e-3 makes the replies shorter. So the first generations mostly teach "finish in time" and
   the early gain on H3 is largely that. Later the model stops writing the `Answer:` line altogether in run B (the share of H3 replies with the line is 0 to 2 percent from generation 25 on; the scorer then reads the last integer of the reply) and swings between 0 and 75 percent in run A.
   Among replies that have the line the accuracy is 85-91 percent in A at the end (46 percent at the base), so the arithmetic of the replies that finish also improved; B has no replies with a line to measure this.
3. **The population around the parent is worse than the parent late in the run:** in generations 50-99 the parent scores 0.93 on the training questions and its 24 perturbed copies 0.83 on average (A: 0.934 and 0.830; B: 0.938 and 0.825). sigma = 1e-3 is a large perturbation for a model this good (the pilot of 06/10 already noted it).
4. **Random steps of the same size destroy the model; the real steps do not.** From checkpoint 50, 50 steps with the SAME noise and the coefficients shuffled (a step of the same size unrelated to the rewards), two independent shufflings per run (`randomwalk-run?-from50.json`; train / H3 / H1 / H2 correct):
   A: real 60 / 112 / 97 / 99 after 50 generations; shuffled 10 / 19 / 90 / 88 and 47 / 71 / 92 / 97. B: real 60 / 89 / 77 / 88; shuffled 41 / 85 / 83 / 91 and 28 / 53 / 81 / 28.
   So over 50 generations the direction matters a great deal for the training family (train 60 against 10-47 of 64), which a one-step comparison cannot see. EXPLORATORY: two walks per run, one starting point.
   The drop of H2 is NOT specific to learning: shuffled walks lower H2 as much or more (A: 88 and 97 against the real 99), so the loss on that family looks like drift of a model whose training score is saturated, not something the gradient does on purpose (two walks, inference).
5. **Held-out accuracy and training accuracy come apart late.** B's H3 reaches 108 at generation 20 and ends at 89 while the training score stays at 94 percent: the 64 training questions are fitted and the weights go on moving. A's H3 stays at 110-116 from generation 30. A stop based on a held-out set (early stopping) would have given B a better model; nothing here implemented that.

## Run C (EXPLORATORY, alpha 5e-4, 60 generations, 5070 Ti only; `runC/`, `analysis-runC.txt`)
Chosen after seeing run A (Addendum 1), so exploratory whatever the result. The step is half as large (rms 1.0e-4 per weight). The 1660S was down, so condition B0x2 was used (two worker processes on the 5070 Ti, policy greedy); 2.5 hours with the offline analysis of B running beside it.

| | train (64) | H3 (128) | H1 (128) | H2 (128) |
|---|---|---|---|---|
| base | 19 | 42 | 77 | 116 |
| run C, generation 60 | 59 | 104 | 99 | 100 |
| run C, generation 55 | 58 | 104 | 104 | 116 |

By the same rules computed at generation 60: S1 true (+62), S3 true (+40), S2 false (+ better than - in 30 of 60, worse in 20, ties 10), S4 false (H2 -16, but H2 was 116 at generation 55: the checkpoint-to-checkpoint swing of H2 is as large as the loss), S5 undefined. **Same verdict class as A and B.**
- The smaller step learns more slowly and in a different shape: the training score stays at 27-31 of 64 until generation 15 and jumps to 57 at generation 20 (A and B were at 34 and 52 of 64 by generation 5), then plateaus at 56-60. H3 ends at 104-109 for generations 40-60, between A (112) and B (89).
- It did not remove the damage on H2: in all three runs H2 swings by up to 28 questions (A) or 16 (C) between neighbouring checkpoints late in the run (A: 115 -> 87 -> 94 -> 83 -> 102; C: 121 -> 114 -> 122 -> 121 -> 116 -> 100). With a 128-question set the final value S4 reads is one noisy point of a wandering curve.
- By phase (positive / negative / tie of parent+ against parent-): generations 0-9 5/4/1 (mean difference +0.002), 10-29 12/6/2 (+0.027), 30-59 13/10/7 (+0.004): the same shape as A and B (no advantage at first, a clear one while learning, none after saturation).
- The 12 replay segments matched their checkpoint hashes.
So half the alpha did not change the verdict and did not make the model steadier; no other alpha or sigma was tried (sigma 1e-3 is large for a model at 0.93 train accuracy: see point 3 above).

## Honest limits (what this does NOT show)
- One model, one task family, one hardware pair, N = 24, 64 training questions, two seed families; held-out questions come from the same generator (another seed). Nothing about other tasks, other methods (no GRPO or random-search baseline), or larger models.
- The gain on H3 is mixed with "answer shorter / finish before 256 tokens" and "drop the answer line"; the decomposition measures the shares but does not separate them. A criterion that excluded format was not met in run B (S5 undefined).
- The criteria S2 and S4 failed; the post hoc readings above (phases, random walks, drift of H2) are explanations found after seeing run A and are not tests; two of them (the random walks) were also repeated on B but remain exploratory.
- Two runs of one configuration give two quite different H3 and H1 trajectories (A: H1 77 -> 97, B: 77 -> 77): the run-to-run spread is large with 128-question sets and N = 24.
- Only the chunk 64 / FP32 / CUDA-engine configuration was used. The 1660S worker took part in the first part of each run (A: until about 00:45, generation 91; B: until about 02:41, generation 49); the machine was unreachable after that
  (the owner restarted it once, after run A's incident), and the worker logs of the 1660S were lost in both runs because the copy back failed. From the totals the 1660S committed 375 of A's 2,400 candidates and 304 of B's (derived: 2,400 minus the local workers' count). The ledger shows
  every result exactly once and the offline replay reproduces every checkpoint hash, so no result depends on who computed which candidate.
- Time per generation: A median 91 s (the cluster, B4x2), B median 117 s (slowed by the offline analysis of A running on the same GPU, and the 1660S gone after generation 48), C below. These are not benchmark numbers.
- The scripts of this folder are experiment code; their pure helpers are tested (`tests/experiments/`, 36 tests, a mutation check of 19 faults: 18 caught, 1 equivalent), `run_learning.py` and `analyze_run.py` are not unit-tested; they were exercised by a 5-generation smoke run (not kept) and by the runs.

