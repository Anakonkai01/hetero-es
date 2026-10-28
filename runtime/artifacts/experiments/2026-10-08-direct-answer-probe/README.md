# Did run D1 teach arithmetic, or to answer directly? (2026-10-08, post hoc, written by the AI)

`direct_answer_probe.py` evaluates, on H1 (256 new level-1 questions, 512-token limit, FP32 greedy), the base model and checkpoints of run D1 (`artifacts/experiments/2026-10-08-learning-v2/`) with
(a) the workload's own system prompt (which asks for step-by-step reasoning ending with `Answer: <integer>`) and (b) a system prompt that asks for the final integer only. Raw: `direct-lrtD1.json`.
Written after seeing run D1's H1 curve; it is an explanation, not a preregistered test.

| model | workload prompt | "only the integer" prompt |
|---|---|---|
| base | 62.1 % (247 characters per reply, 73 % with an `Answer:` line) | **77.0 %** (3 characters) |
| D1, generation 15 | 84.0 % (96 characters, 0 % with a line) | 76.6 % |
| D1, generation 40 | 82.4 % (88 characters, 20 % with a line) | 68.8 % |

## What it says (numbers measured; the reading is mine)
- The base model reasoning in text (the workload's prompt) is WORSE at two-digit arithmetic (62.1) than the same base model asked to give only the number (77.0). Run D1 moved the model from long replies (247 characters) to short ones (about 95): with the workload's prompt it
  now scores 82 to 84 percent. **Against the right baseline (the base model's best way of answering, 77.0) the gain is +5 to +7 points: 256 questions, a standard error of about 2.5 to 3 points on each accuracy: borderline (about 2 standard errors) and from one run.**
  Most of the +20 points of the preregistered criterion P1 (62.1 -> 84.0) is "stop reasoning in text and answer directly", which the base model could already do when asked.
- The trained checkpoints asked for only the integer are not better than the base asked the same way (76.6 and 68.8 against 77.0): the weights did not learn to calculate better in that mode.
- Limits: one run, one prompt wording for the direct mode, one family; the gap between 77.0 and 82 to 84 may be real (a hybrid reply: a short reasoning and the number) but this run cannot say.
