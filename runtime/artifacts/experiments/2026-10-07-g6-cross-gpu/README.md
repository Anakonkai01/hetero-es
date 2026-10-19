# G6: why the same candidate can score differently on two GPUs, and what removes it (07/10/2026)

The open finding of G4/G5: candidate 21 of generation 0 scored 0.25 on the 5070 Ti and 0.1875 on the 1660S; "every chunk above 1 changes some answers". The audit
noted that the two machines also ran different torch and transformers, so the hardware could not be blamed. This folder is the study that followed. Everything
here was run on the SAME software on both machines: torch 2.13.0+cu132, transformers 5.17.0 (the 5070 Ti in the conda environment `heteroes-match`, NumPy
2.5.3; the 1660S in its venv, NumPy 2.5.2, Python 3.14.4). The scripts are `scripts/cross_gpu_sweep.py` and `src/heteroes/eval/diagnostics.py`; both
are in the repository and have tests. The code of the 5070 Ti runs was at the commits of the branch `feat/audit-hardening-g6` (the `code` field of each
JSON header; `git_dirty` is only the unrelated untracked notebook).

## 1. The ladder: is it the padding, the tokenization path, or the numbers? (`ladder*.json`, 5070 Ti, the parent weights and 32 candidates)

For every state (33) and prompt (16) the answer produced one prompt per call (the reference path) is compared with the same prompt in another call shape.

| call shape | torch 2.13 / transformers 5.17, FP16 | torch 2.10 / transformers 5.5, FP16 | FP16 but the output projection in FP32 | **forward pass in FP32 from the same FP16 weights** |
|---|---|---|---|---|
| a batch of one, padding enabled (no pad is added) | 0 of 528 | 0 of 528 | 0 | 0 |
| batches of two, left padded | 9 of 528 | 9 of 528 | 8 | **0 of 528** |
| one batch of 16, left padded | 16 of 528 | 16 of 528 | 17 | **0 of 528** |

Identical counts on the two software stacks: the stack is not the cause. A batch of one with padding enabled does not differ: the tokenization path is not the cause
either. What differs is a row that is padded. Computing only the last matrix in FP32 changes nothing (the noise is in the layers, not in the last projection). The margin
between the two best scores at every flip (`margins_at_the_flip` in the files) is 0 to 0.094 on scores of 16 to 32, where FP16 has a spacing of 0.0156 and 0.0312: ties
and one-unit differences of the rounding, as expected from numerical noise. Never a large margin.

## 2. The sweep: the same 120 candidates (seeds 0 to 119, sigma 1e-3) on both GPUs (`sweep-*.jsonl`, `compare-*.json`)

Each candidate is perturbed with the package function, its 16 prompts are answered one at a time, and for each prompt the text, the token ids and the margin at
every step are recorded. `compare` joins two files by seed and prompt.

| comparison (120 candidates, 1,920 prompts) | candidates with a different answer text | prompts with a different text | candidates with a different REWARD | margin at the flip |
|---|---|---|---|---|
| **FP16, 5070 Ti against 1660S** | 33 (27.5 %) | 36 (1.9 %) | 1 (seed 43: 0.25 against 0.1875) | median 0.0, largest 0.043 |
| **FP32 forward pass, 5070 Ti against 1660S** | **0** | **0** | **0** | none |
| 5070 Ti, FP16 against FP32 | 29 | 37 (1.9 %) | 1 | median 0.003, largest 0.048 |
| 1660S, FP16 against FP32 | 35 | 41 (2.1 %) | 2 | median 0.003, largest 0.048 |

Reading it:

- In FP16, one candidate in 4 has a different answer text on the other GPU, and about 1 candidate in 120 a different reward (the case of G4/G5: the reward changes only when
  a flipped answer changes right to wrong or back). All the flips are exact ties or one-unit differences of the FP16 scores: the numerical noise of two kernels, not a bug.
- With the forward pass in FP32 (the weights, the noise, the perturbation and the update stay as they are: `Recipe.eval_dtype`, contract section 15), the two GPUs gave **the
  same answer text for every one of the 1,920 prompts**. This is a checked level, not a guarantee: with no difference in 1,920 prompts the 95 percent upper bound of the
  rate is about 0.16 percent of prompts (the rule of three), and about 2.5 percent of candidates for a difference in at least one prompt.
- The FP32 evaluation changes the answers of about 2 percent of the prompts relative to FP16 on the SAME GPU and the reward of 1 or 2 candidates in 120. It is a different
  recipe: results of FP16 runs and FP32 runs are not bit-comparable (that is why it is an option of the recipe and has its own hash).

## 3. What it costs and what it buys (5070 Ti, profiles in `../2026-10-07-g6-profiles/`)

| the 16 prompts of the workload, one evaluation | time |
|---|---|
| FP16, one prompt per call (the reference path of G3 to G5) | 0.79 s |
| FP16, one batch of 16 (not exact) | 0.13 s |
| FP32, one prompt per call | 0.99 s |
| **FP32, one batch of 16 (exact in the 33 states probed: safe chunk 16)** | **0.16 s** |

So the exact evaluation is 5 times faster than the reference path. The price: about 2 GB of GPU memory more (a float32 copy of the model), which a 6 GB card can pay (the
1660S ran the sweep).

## What is NOT shown

One software stack (two machines), 120 candidates per setting, one model, one workload of 16 prompts, greedy decoding, sigma 1e-3; no other GPU; the candidates were
evaluated one at a time (the chunk probe of the FP32 batches on the 1660S is in `../2026-10-07-g6-profiles/`). The decision to make FP32 the default of the experiments is the
owner's (O8): the code keeps FP16 as the default.
