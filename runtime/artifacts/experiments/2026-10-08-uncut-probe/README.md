# Is the gain of the learning runs only "finish before 256 tokens"? (2026-10-08, written by the AI after the runs)

Question that follows from `artifacts/experiments/2026-10-07-learning-runtime/README.md` (point 2: 36 of 64 base replies hit the 256-token limit): what does the base model score if it is
allowed to finish (512 tokens), and what do the trained checkpoints score at 512? `uncut_probe.py` evaluates, with the same questions and the same FP32 greedy decoding, with the token limit
of the workload (256) and with 512. Sets: H3 = 128 new level-3 questions (generator seed 20261008, none a training question), and the 64 training questions. Raw: `uncut-lrt{A,B,C}.json/.log`.
Written AFTER seeing the runs; it is an explanation, not a preregistered test.

## H3 accuracy (% of 128), token limit 256 / 512

| checkpoint | 256 tokens | 512 tokens | replies with an `Answer:` line (512) |
|---|---|---|---|
| **base model** | **32.8** | **81.2** | 70 |
| run A, gen 10 | 81.2 | 81.2 | 70 |
| run A, gen 20 | 74.2 | 74.2 | 0 |
| run A, gen 50 | 88.3 | 88.3 | 5 |
| run A, gen 100 | 87.5 | 87.5 | 45 |
| run B, gen 5 | 74.2 | 74.2 | 84 |
| run B, gen 20 | 84.4 | 87.5 | 8 |
| run B, gen 50 | 78.9 | 78.9 | 0 |
| run B, gen 100 | 69.5 | 69.5 | 0 |
| run C, gen 20 | 78.9 | 81.2 | |
| run C, gen 40 | 85.2 | 85.9 | |
| run C, gen 60 | 81.2 | 82.0 | |

Training questions (64): base 29.7 -> 81.2 (512 tokens); the trained models 87.5 to 95.3 at either limit.

## What it says (measured numbers; the reading is mine)
- **The base model is already at 81.2 percent on H3 when it is allowed 512 tokens.** The 32.8 percent at 256 tokens was mostly the cut: the model reasons at length and the answer line never comes.
- The trained checkpoints give the same score at 256 and at 512 (they finish early): ES taught the model to be brief enough to finish. **Against the right baseline (81.2) the final H3 of the runs is +6.3 points (run A, 8 questions), -11.7 points (run B) and +0.8 points (run C):
  the average is about zero and one question of 128 is 0.8 points, the standard error of one score about 3.5 points.** Run B ends clearly below the base model's real ability.
- So the strong result of the first analysis ("H3 42 -> 112") is, to a first approximation, **"finish before the token limit" and not "calculate better"**. The training score is 12.5 points above the base at 512 tokens (81.2 -> 93.8 of 64 questions), which is the part that is fitted to those 64 questions.
- This does not touch the correctness or speed results of the runtime (replay, hashes, benchmark): only the interpretation of the learning runs. The criteria S1 to S5 were met or not exactly as reported; S1 used the 256-token baseline, which is the confound.
- Caveat: one decoding setup, one model, three runs; "base at 512" is one measurement.
