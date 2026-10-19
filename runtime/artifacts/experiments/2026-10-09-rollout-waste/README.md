# How much of the rollout is spent on answers that are already finished? (09/10/2026)

Written by the AI, **not reviewed by the owner**. `answer_lengths.py` (output: `answer_lengths.out`, run twice, same numbers): the 128 questions of `cot_l1_q128`, parent weights, FP32 forward pass, greedy, `max_new_tokens` 256, on the 5070 Ti, after one warm-up. It records the real length of every answer and the number of decoding steps and the time of every `generate()` call.

## Measured
| | chunk 64 (2 calls) | chunk 128 (1 call) |
|---|---|---|
| steps per call | 256 and 173 | 256 |
| time per call | 3.99 s and 2.35 s | 7.2 s |
| ms per decoding step | 15.6 and 13.6 | 28.2 |
| slots computed (steps x batch) | 27,456 | 32,768 |
| slots that held a real answer token | 12,041 | 12,041 |
| useful fraction | 0.44 | 0.37 |

Answers: mean 94 tokens, median 81, minimum 5, maximum 256 (1 of 128 reaches the limit); the prompt is 43 tokens. `generate()` of the library stops a batch only when EVERY answer in it has finished, so a finished answer keeps being computed (as padding) until the longest one ends.

## What it shows
* More than half of the computed token slots are wasted (0.44 and 0.37 useful).
* The time per step is proportional to the batch (15 ms at 64, 28 ms at 128, about 1.4 ms fixed + 0.21 ms per sequence), so a bigger chunk saves nothing: this explains why chunk 128 was not faster than chunk 64.

## What it does NOT show
* One GPU, the parent weights only (perturbed candidates have other lengths), one run of 128 questions. The linear model (fixed + per sequence) is a two-point fit, not a measurement of the kernels; the cause of 0.21 ms per sequence-step is NOT known (a profile is needed).
* Nothing has been implemented; any gain from skipping finished answers is an estimate (see the chat of 09/10).
