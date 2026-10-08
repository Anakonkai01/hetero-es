# Third machine: RTX 3060 12 GB (Windows 11 + WSL2 Ubuntu 26.04), borrowed on 08/10/2026

Written by the AI, **not reviewed by the owner**. Status: IN PROGRESS (the profile and the three-machine runs are not done yet; this README is updated when they are).

## The machine
RTX 3060 (Ampere, sm_86), driver 615.78 (Windows side, CUDA 13.4), WSL2 kernel 6.6.87, Ubuntu 26.04.1, Python 3.14.4 (the same as the 1660S), 31 GB RAM. Reached over SSH through Tailscale (`desktop-qp0nta7`). `machine-3060.txt`, `pip-freeze-3060.txt`.
Software: `torch 2.13.0+cu132`, `transformers 5.17.0`, `numpy 2.5.3` (as the 5070 Ti; the 1660S has 2.5.2), the CUDA libraries as pip chose them except `nvidia-nvjitlink`, which pip took at 13.4.92 and was pinned to 13.3.33 to match the other two machines. The model was downloaded from Hugging Face at the pinned revision `7ae557604adf67be50417f59c2c2f167def9a775`. The repository came by `git bundle` at commit `d1cd21b`.

## Results so far
1. **Test suite on the 3060 with the real model: 2058 passed, 4 skipped, 2 failed** (`tests-3060.log`, 166 s). The two failures are `test_qwen_candidate_matches_all_the_recorded_evidence` and `test_base_model_reproduces_the_probe_outputs_text_for_text`: both compare the FP16 evaluation with the answers recorded on 2026-09-29 and one answer differs (`674` against `664`). That is the known FP16 difference between GPUs (G6), not a new defect; the system evaluates in FP32 by default since decision O8. These two tests pass on the 5070 Ti and on the 1660S, so on this suite the 3060 is the first machine that does not reproduce the FP16 record.
2. **CUDA noise engine: equal on all three GPUs.** `cuda_engine_crossgpu.py` on the 3060 (`cudaengine-3060.json`) against `../2026-10-07-g7-restore-tradeoff/cudaengine-5070ti.json` and `-1660s.json`: the 10 hash fields (the noise fingerprint, the weights after a perturbation, after an update, after the restore) are equal in the three files.
3. **Cross-GPU sweep (120 candidates, seeds 0 to 119, 16 prompts each = 1,920 answers), the 3060 against the G6 files of the other two** (`compare-*-vs-3060.json`):

| evaluation | against | candidates with a different answer | candidates with a different reward | prompts with a different answer |
|---|---|---|---|---|
| **FP32 (the default)** | 5070 Ti | **0** | **0** | **0 of 1,920** |
| **FP32 (the default)** | 1660S | **0** | **0** | **0 of 1,920** |
| FP16 | 5070 Ti | 30 (25%) | 0 | 35 (1.8%) |
| FP16 | 1660S | 36 (30%) | 1 | 40 (2.1%) |

So the 3060 agrees bit for bit on the noise engine and on every FP32 answer of this sweep, and disagrees at FP16 at about the rate that the two other GPUs disagree with each other (33 of 120 candidates in G6).

## What this does NOT show (yet)
Only 120 candidates and one 16-prompt workload were swept on the 3060; the long workload `cot_l1_q128` at chunk 64 has not been compared across the three machines until the three-machine benchmark has run; no timing result yet; WSL2 (a Linux kernel in a Windows host) is one platform, native Windows was not tried; the software of the 3060 is not byte-identical to the others (NumPy patch version, Python minor version equal to the 1660S only).
