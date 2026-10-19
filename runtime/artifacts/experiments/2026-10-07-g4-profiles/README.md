# G4: profiles of the two GPUs, and the admission predictions (07/10/2026)

Produced by `scripts/profile_worker.py` (profiles) and `scripts/predict_admission.py` (predictions); the model code is `src/heteroes/profile.py`
and `src/heteroes/admission.py`. Workload: the frozen 16-prompt arithmetic set, `Qwen2.5-0.5B-Instruct@7ae55760`, FP16, sigma 1e-3.

## What is here

| file | what it is |
|---|---|
| `profile-5070ti.json`, `profile-1660s.json` | **v1**: chunk probe with 2 perturbed candidates (+ the parent weights). The 1660S file also holds the link and the full synchronization measured against `scripts/serve_weights.py` over the direct cable. |
| `profile-5070ti-v2.json`, `profile-1660s-v2.json` | **v2**: the same with 32 perturbed candidates. The 5070 Ti file was measured while the 1660S profile ran against the same machine (weights served, CPU shared): its `update` (12.7 s per candidate) is **contaminated, do not use it**. |
| `profile-5070ti-v2b.json` | the 5070 Ti again, alone, with 32 candidates: the clean numbers of v2 (update 4.25 s per candidate). |
| `prediction-n8.json`, `prediction-n24.json` | the admission prediction, **written from the v1 profiles before any benchmark run** (`written_at_utc` and the git commit are inside). Never edited. |

## What was measured

| | 5070 Ti | 1660S |
|---|---|---|
| candidate at chunk 1 (median of 5): perturb / rollout / restore | 4.5 s: 3.67 / 0.72 / 0.14 | 17.1 s: 9.24 / 7.35 / 0.49 |
| peak GPU memory of a candidate | 1.07 GB of 16 GB | 1.07 GB of 6 GB |
| full synchronization from the 5070 Ti (v1) | none (it holds the weights) | 21.9 s: transfer 8.5 + load 4.1 + rehash 9.3 (116 MB/s, RTT 0.8 ms) |
| update on the coordinator | 4.25 s per candidate (v2b; v1 median 6.18 of 3 noisy samples) | not measured (it is the coordinator's job) |
| noise self-test, restore bit-exact, chunk 1 gives the answers recorded on 29/09 | yes, yes, yes | yes, yes, yes |

The CPU noise generation (perturb 3.67 s / 9.24 s, and the same cost inside the update) is the biggest part of everything: the 1660S is 1.9x slower on
the CPU part and 10x slower on the GPU part (rollout).

## The safe chunk: what the first profile got wrong

A "chunk" is the number of prompts in one `generate()` call (the whole prompt set is always evaluated; only the grouping changes). A chunk is *safe*
if it fits in memory and gives the **same answer text** as one prompt at a time. v1 (2 perturbed candidates) said: 5070 Ti chunk **16** is safe,
1660S chunk 1. v2 (32 perturbed candidates) says: **chunk 1 on both**; every larger chunk changed some answer text (5070 Ti: 10 to 14 differing
answers over 33 states for chunks 2, 4, 8, 16; 1660S: 8 to 13). Batching with left padding is not numerically exact in FP16, and a difference that
shows in about 4 percent of the candidates needs about 30 candidates to be seen (73 percent chance; with 2 it is 8 percent).
The benchmark of v1 trusted chunk 16 and the result differed from chunk 1 (`../2026-10-07-g4-admission-b2/README.md`): the weak probe is a
finding of its own. With v2, H0 has nothing to size: both workers use chunk 1. Even 32 candidates do not prove a chunk exact: it is a
checked level (MASTER section 8), not a guarantee.
