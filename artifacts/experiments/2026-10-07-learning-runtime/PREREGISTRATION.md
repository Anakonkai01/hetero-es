# Learning experiment on the distributed runtime — criteria written BEFORE the main runs (2026-10-07, night)

Written by the AI (the owner approved the plan, then went to sleep; the owner has not seen this file). Branch `feat/learning-experiment`.

## Question
With the whole runtime (coordinator + two pull workers on the 5070 Ti and the 1660S, CUDA noise engine, FP32 evaluation, tail-aware dispatch), does ES raise the
accuracy of Qwen2.5-0.5B-Instruct on questions it never trained on, and is the gain due to the DIRECTION of the update, not to the mere act of perturbing?

## What I had seen before writing this (so the reader can discount it)
Measured on the 5070 Ti, FP32, chunk 64, before this file existed (scratch scripts, not kept in the repo; the numbers are re-measured by `analyze_run.py`):
- base model on the 64 training questions (`cot_l3_q64`, level 3 word problems): 19/64 = 0.297; of the 64 replies **36 have no `Answer:` line** (they are cut at the
  256-token limit), 19 are right, 9 have a wrong integer;
- base model on held-out sets of 128 questions with another generator seed (20261008): level 3 = 42/128, level 1 = 77/128, level 2 = 116/128 (level 2 is near the ceiling);
- a single random perturbation (CUDA engine, sigma 1e-3, seeds 1, 2, 3) of the base model scores 0.75, 0.72, 0.72 on the training questions (4 replies of 64 without
  an answer line, instead of 36); at sigma 1e-4 it scored 0.19 and 0.19, at 3e-4 0.56 and 0.25. And the first benchmark generations (G7) had candidates at 0.67-0.70.
**Consequence:** on this workload a large part of any "improvement" can be the model learning to answer SHORTER (finish before 256 tokens) and not to calculate better.
The perturbation itself already does that. That is why the criteria below include a control that uses the same noise, and a decomposition of the accuracy
(answer-line rate, accuracy among replies that have an answer line).

## Setup (fixed now)
- Runtime: `run_learning.py` of this folder (uses `scripts/cluster_runner.py`): coordinator on the 5070 Ti with two worker processes on it and one worker on the 1660S,
  policy B4 (tail-aware), `--noise-engine cuda`, `--workload cot_l3_q64`, `--eval-dtype float32`, worker chunk 64. N = 24 candidates, sigma = 1e-3, alpha = 1e-3
  (the update has a root-mean-square step of alpha / sqrt(N) = 2.0e-4 per weight, measured as `applied_l2 / sqrt(494,032,768)` in the G7 benchmark logs),
  100 generations. Run A: experiment id `lrtA`. Run B (replication, other noise): experiment id `lrtB`, everything else the same.
- Reward of the candidates: the 64 training questions (`make_questions(64, 3)`), exact integer match after the last `Answer:` (the package's `cot_workload`).
- Held-out sets (`learnlib.py`, generator seed 20261008, never used for any decision, questions equal to a training question removed): H3 = 128 questions of level 3
  (the training family), H1 = 128 of level 1 (two-digit operations, other family), H2 = 128 of level 2 (three operands, other family).
- Checkpoints: the weights of generations 0, 5, 10, ..., 100 are kept (hard links of the published files; the runtime itself keeps only the last 3).
- Offline analysis (`analyze_run.py`, after the run, uses the ledger's update records): from each checkpoint it replays the recorded updates to rebuild every parent in
  between and checks the hash of the next checkpoint (so the replay is verified, not assumed); for EVERY generation g it measures on the training questions
  parent_g, parent+_g (= parent_{g+1}) and **parent-_g** (the CONTROL: same parent, same candidates, same noise, same rewards, update with -alpha);
  at every 10th generation it also measures a second control **shuffled** (the same coefficients permuted at random: a step of the same size in a direction unrelated to the
  rewards) and the three held-out sets for parent+, parent- and shuffled; for every checkpoint (every 5th generation) it measures the held-out sets and the decomposition.

## Criteria (fixed now, before the main runs; all are on run A, run B is the replication judged by the same rules)
- **S1 (improvement on new questions of the same family):** H3 accuracy of the generation-100 weights is at least 8 questions of 128 (0.0625) above the base model's H3 accuracy.
- **S2 (the direction matters):** train(parent+_g) - train(parent-_g) > 0 in at least 70 of the 100 generations AND its mean over the generations is positive. (If the
  directions carried no information the count would be about 50 +- 5; 70 is four standard deviations away. The anti-step is exact: same parent, same noise.)
- **S3 (training progress):** train accuracy of the generation-100 weights is at least 0.10 above the base model's (0.297, i.e. at least 0.397).
- **S4 (no damage elsewhere):** H1 and H2 accuracy of the generation-100 weights are each not more than 8 questions of 128 below the base model's.
- **S5 (not only a shorter reply; reported, not decisive):** accuracy among the H3 replies that HAVE an answer line, at generation 100, is not more than 0.05 below the base
  model's. Reported next to the answer-line rate and the mean reply length, whatever the result.
- Verdicts. S1 and S2 and S3 and S4 all true -> "a learning signal on this workload". Plus S5 true -> "and it is not explained by shorter replies alone". Anything less ->
  "no evidence of learning in this experiment" (NOT "ES does not work"). S2 alone true with S1 false -> "the direction carries information but 100 generations did not move held-out accuracy".
- Run B must reach the same verdict class as run A to call the result replicated. If A and B disagree, both are reported and the claim is "not replicated".

## Stop rules and what is not decided here
- A run stops early only for a NaN/Inf reward or weight (the runtime refuses those), a failure the supervisor cannot recover (3 restarts of the coordinator or 5 of a worker),
  or the deadline of the session (all runs must be finished by 07:45 on 2026-10-08; whatever is complete by then is analysed, incomplete runs are reported as incomplete).
- Not decided here: any other alpha or sigma. If time remains, a third run with another alpha or sigma is EXPLORATORY and will be labelled so.
- Limits stated in advance: one model, one workload family, one hardware pair, N = 24, 64 training questions (one question = 1.6 points), 128 held-out questions per set
  (one question = 0.8 points, a standard error of about 4 points at accuracy 0.5), 100 generations, two seed families. Held-out questions come from the same generator
  (other seed) as the training ones. No comparison with another algorithm. A positive result is evidence for THIS setting only.
