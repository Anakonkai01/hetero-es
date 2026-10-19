# Short learning experiment on one GPU, 2026-10-06

Question: with the code of the package (perturb, restore, standardized reward, FP32 update; manifest seeds), does ES raise the accuracy of
Qwen2.5-0.5B-Instruct on arithmetic questions it has never seen? The criteria were written BEFORE the runs (`PREREGISTRATION.md`, with an
addendum written after runs 1 and 2). Machine: RTX 5070 Ti, conda env `ai`, commit `588fa71` (code of the package), about 21 to 23 minutes per run.

## Setup (as run)

- Data (`dataset.py`, fixed seed, no question of the frozen 16-question workload): three types of questions where the base model is neither at 0 nor at 1
  (subtraction of two 2-digit numbers; 1-digit x 2-digit product; 2-digit x 2-digit product). Train set 96 questions (reward of the candidates), held-out set
  96 questions (never used for any decision), 32 of each type in each. Base model: train 0.7292, held-out 0.6667. The types were chosen after measuring the base
  model on a pool of 280 questions (`pool.json`: the other types are near 0 or near 1, where candidates cannot differ).
- Per generation: N = 8 candidates, sigma = 1e-3, seeds `derive_seed(experiment, generation, index)`; each candidate is perturbed, scored on the train set and restored
  (bitwise verified); `apply_es_update_` with alpha gives the next model (parent+). **Control** from the same parent with the same candidates and noise: the
  update with -alpha (parent-, the "anti-step"); the run continues from parent+.
- Reward: exact integer match (the workload recipe), greedy decoding, 16 new tokens.

## Results

| Run | alpha | seeds | held-out before -> after 10 generations | S1 (>= +6 questions) | S2 (+ better than - in >= 8/10) | S3 (train gain of + > 0) |
|---|---|---|---|---|---|---|
| 1 | 3e-3 | learn | 0.667 -> 0.469 (**-19** questions) | NO | YES (10/10) | NO (-0.022) |
| 2 | 1e-3 | learn | 0.667 -> 0.885 (**+21**) | YES | YES (9/10) | YES (+0.017) |
| 3, replication | 1e-3 | learn-b | 0.667 -> 0.823 (**+15**) | YES | **NO (7/10)** | YES (+0.010) |

Train accuracy after 10 generations: 0.510, 0.896, 0.833 (before: 0.729). Details per generation and per type: `analysis.txt`.

- alpha = 3e-3 (about one sigma per coordinate) is too large: the model gets worse (9 held-out questions gained, 28 lost), although the direction still carries information
  (the + step is better than the - step in 10 of 10 generations).
- alpha = 1e-3 improved the held-out accuracy in two independent families of seeds (+21 and +15 questions of 96). Run 2 met all three criteria; run 3 met S1 and S3 but
  **not S2** (7 of 10 generations, below the threshold of 8 fixed in advance; the mean difference is still positive, +0.034). By the rule written in advance only run 2 is a full success.
- In run 2 the gain is mostly in subtraction (21 -> 32 of 32 held-out), then 1x2 products (20 -> 26) and 2x2 products (23 -> 27); 23 held-out questions went from wrong to right and 2 the other way.
  In run 3 (`outputs_seedfamily_b.json`): the output is only an integer in 96 of 96 texts at the start and 95 of 96 at the end, the mean length did not change (2.6 characters), and all 17
  gained questions had a WRONG integer at the start (for example `88 - 45`: `33` -> `43`). So the gain is not a change of the format of the answer.
- Observed, not tested: the candidates score on average below their parent on the train set (by 0.06 to 0.11), and only 0 to 3 of 8 beat it in a generation: sigma = 1e-3 is a strong perturbation for these
  questions. A smaller sigma was not tried.

## Limits (read before quoting any number)

- One model, one family of arithmetic questions, 10 generations, N = 8, one machine. One question is 1.04 points: differences of one or two questions are noise.
- Two values of alpha were tried and the better one was singled out after seeing both; the replication is the answer to that, and it did not meet S2. No p-values were computed.
- The held-out questions come from the same generator as the training questions: this measures generalisation to new instances of the same task, not to other tasks.
- The reward is exact match on one number; nothing was said here about reasoning, other tasks, or about other methods (no comparison with GRPO or with a baseline of random steps beyond the anti-step control).
- Runs 1 and 2 were made with the script before the optional flag `--save-outputs` was added (the file here is the final version: the flag is the only difference);
  the model of the end of a run is not saved (only the correctness vectors of every evaluation and, for run 3, the held-out output texts).
- The scripts are experiment scripts, not tested package code. Held-out and train evaluations of parent+ and parent- were measured at every generation, but only the train rewards of the
  candidates were used by the update.

## Files and how to reproduce

`python learn.py --alpha 1e-3 --generations 10 --experiment-id learn --output <new file>` (run 2); `--experiment-id learn-b --save-outputs <file>` (run 3); `--alpha 3e-3` (run 1).
The experiment id selects the seeds. Evaluation of one question takes about 26 ms; the CPU noise generation (perturb and the two updates) dominates: about 2 minutes per generation.

| File | What it is |
|---|---|
| `PREREGISTRATION.md` | question, setup, criteria S1 to S3 (written before the runs) and the addendum (after runs 1 and 2) |
| `dataset.py`, `learn.py`, `analyze.py`, `analyze_outputs.py`, `run_all.sh` | the scripts (`run_all.sh` ran runs 1 and 2 one after the other) |
| `pool.json` | 280 questions of 7 types with the base answers, used to choose the types |
| `pilot.log`, `pilot_alpha3e-3.json` | a 2-generation pilot of run 1 (the same first two generations) |
| `run_alpha3e-3.json/.log`, `run_alpha1e-3.json/.log`, `run_alpha1e-3_seedfamily_b.json/.log` | the three runs: every generation with seeds, candidate rewards, update report, correctness of every question for parent, parent+ and parent- |
| `outputs_seedfamily_b.json` | held-out questions and the output texts at the start and at the end of run 3 |
| `analysis.txt` | the output of the analysis scripts for the three runs |
| `SHA256SUMS` | checksums of the files of this folder |
