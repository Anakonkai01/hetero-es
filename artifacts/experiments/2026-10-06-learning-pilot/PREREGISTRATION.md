# Short learning experiment, written BEFORE the runs (2026-10-06)

Question: with the code of the package, does ES (population of perturbed candidates, standardized reward, FP32 update)
raise the accuracy of Qwen2.5-0.5B-Instruct on arithmetic questions it has never seen?

Data (dataset.py, fixed seed; none of the 16 frozen workload questions): three types where the base model is neither at 0 nor at 1:
subtraction of two 2-digit numbers, 1-digit x 2-digit product, 2-digit x 2-digit product (base accuracy 0.65, 0.55, 0.82 on a first pool).
Train set 96 questions (32 per type) = the reward of the candidates. Held-out set 96 questions (32 per type), never used for any decision.
Reward = exact integer match, same system prompt, greedy, 16 new tokens (the workload recipe).

Loop (per generation, N = 8 candidates, sigma = 1e-3 as everywhere else):
 1. seeds = derive_seed("learn", generation, index); candidates are perturbed, scored on the TRAIN set, restored (bitwise-verified).
 2. update with apply_es_update_ (alpha = A) -> parent+ ; measure train and held-out accuracy of parent+.
 3. CONTROL, same parent, same candidates, same noise: update with -A ("anti-step") -> parent- ; measure the same.
 4. continue from parent+ (the real trajectory).

What counts as a learning signal (fixed now, before any result):
 S1  held-out accuracy after 10 generations is at least 6 questions (0.0625) above the held-out accuracy before the first generation;
 S2  the paired difference D_g = held-out(parent+) - held-out(parent-) is positive in at least 8 of the 10 generations and its mean is positive;
 S3  the mean over generations of train(parent+) - train(parent) is positive.
All three -> "a learning signal under this recipe". Anything less -> "no evidence of learning in this experiment" (NOT "ES does not work").
Why 6 questions: a single random perturbation at sigma = 1e-3 changed the score of the 16-question workload by one question; on 96 questions a
random coherent step is expected to move the score by a few questions either way (this is an expectation, it is measured by the control S2).

Alpha: 3e-3 first (step of about 1 sigma per coordinate: z has unit variance, so the update has a standard deviation of about alpha / sqrt(N) = 1.06e-3);
then 1e-3; a larger alpha only if both are inconclusive and the model is not damaged. Alpha is chosen from this small grid, NOT by looking at held-out results of
a single run: every run is reported.

Limits stated in advance: one model, one task family, 10 generations, 96 + 96 questions (one question = 1.04 points), a single seed family,
reward measured by exact match. A positive result is evidence for THIS setting only. Held-out questions come from the same generator as the
training questions (same distribution), so this measures generalisation to new instances, not to other tasks.

## Addendum, written AFTER runs 1 and 2 (2026-10-06, 02:10): replication
Run 1 (alpha 3e-3): S1 no (held-out -19 questions), S2 yes (10/10), S3 no: the step is too large, the model drifts to worse accuracy.
Run 2 (alpha 1e-3): S1 yes (+21), S2 yes (9/10), S3 yes.
Both runs are reported. Because the positive alpha was singled out after seeing both, one replication is run with another family of seeds:
experiment id "learn-b" (all noise directions different), alpha 1e-3, the same data, N, sigma and criteria S1-S3 (unchanged). It also saves the held-out output
texts at the start and at the end, to look at WHAT changed (arithmetic or only the format of the answer). The script got one optional flag for that
(--save-outputs); runs 1 and 2 were made without it. No further run is planned in this session; a third family or other sigma would be exploratory.
