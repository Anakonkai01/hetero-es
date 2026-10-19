# O2 perturbation arithmetic and noise engine, cross-machine check, 2026-10-03

Question: how must `theta' = theta + sigma * eps` be computed so that every machine gets the same bits?
Decision taken from this evidence: option (c), see `docs/numerical-contract.md` section 5 (O2).

Script: `scripts/o2_cross_gpu_check.py` at commit `7b73e0343fbc3c22e33753733249914406012bef`
(self-contained: a copy of the noise engine, Qwen2.5-0.5B-Instruct at revision
`7ae557604adf67be50417f59c2c2f167def9a775`, candidate seed 0, sigma = float32(1e-3), all 494,032,768 weights).

## Environments

| Label | GPU | Compute cap. | torch / CUDA | NumPy | Python | How it was run |
|---|---|---|---|---|---|---|
| 5070ti | RTX 5070 Ti | 12.0 | 2.10.0+cu128 / 12.8 | 2.4.5 | 3.12.13 | local, conda env `ai` |
| 1660s | GTX 1660 SUPER | 7.5 | 2.13.0+cu132 / 13.2 | 2.5.2 | 3.14.4 | `heteroes-worker-1660s`, repo cloned at the commit above, `pytest tests` also run there |
| colab | Tesla T4 | 7.5 | 2.11.0+cu130 / 13.0 | 2.1.3 | 3.13.15 | Colab free tier, script pasted into one cell |
| kaggle | Tesla T4 | 7.5 | 2.11.0+cu128 / 12.8 | 2.1.3 | 3.13.15 | Kaggle free tier, script pasted into one cell |

## Files

| File | What it is |
|---|---|
| `5070ti_o2_check.txt`, `5070ti_pytest.txt` | full output of the script and of `pytest tests -v` (117 passed) on the 5070 Ti host, at the commit above |
| `1660s_o2_check.txt`, `1660s_pytest.txt` | the same on the 1660S (copied with `scp`; SHA-256 verified on both machines). `pytest`: 117 passed |
| `colab_t4_result.json`, `kaggle_t4_result.json` | the `RESULT_JSON` line printed by the script. **Transcribed by hand from the pasted notebook output** (the original notebook output is not stored here). The full logs were pasted into the chat, they said PASS on every check |

Not stored: pip freeze of the 1660S, Colab and Kaggle (not recorded when the runs were made).

## Result (whole-model SHA-256 of the perturbed weights; same prefix = bit-identical on every element)

| Method | 5070ti | 1660s | colab | kaggle |
|---|---|---|---|---|
| B  gpu fp32: mul, then add, then half (option c); also F numpy fp32, G torch cpu fp32, L per chunk | `8aa3eb9af895cb4a` | `8aa3eb9af895cb4a` | `8aa3eb9af895cb4a` | `8aa3eb9af895cb4a` |
| A  gpu fp16 `add_(alpha)` (option a); also C, K and I (emulated FMA) | `ce33fa3262716a57` | `ce33fa3262716a57` | `ce33fa3262716a57` | `ce33fa3262716a57` |
| J  numpy exact float64, single rounding | `d1f6ca0ca4eb2270` | `d1f6ca0ca4eb2270` | `d1f6ca0ca4eb2270` | `d1f6ca0ca4eb2270` |
| E  gpu all steps in fp16 | `5f66dbeb14ae46a5` | `5f66dbeb14ae46a5` | `1546103c22789be1` | `1546103c22789be1` |
| H  torch cpu fp16 `add_(alpha)` | `f92b509e4e8fa133` | `27199c6920659b15` | `add2f41fe1088365` | `add2f41fe1088365` |

Other checks that passed in all four environments: 10 golden vectors (probe and production), 290 tensors /
494,032,768 elements / one alias group, probe and production schema hashes, full-model noise hash
`816c15300c45ca9e…` (2,105 chunks) equal to the one recorded by the 2026-09-29 probe.

Differences between (c) and (a): 167 of 494,032,768 elements (91 only in the sign of zero, 76 real, max 1 ULP).
`add_` on the GPU versus `add_` on the CPU: 47.3 to 48.8 million elements. (c) versus all-fp16 steps: about 32 million.

## Limits

- Only these four environments, all x86_64 Linux; one seed (0), one sigma (1e-3).
- The perturbation was computed by the script, not by a function of the package (none exists yet).
- Not covered: restore, predictions, reward (the other items of the cross-machine gate).
- The cause of the differences in methods E and H is not known (nothing was verified beyond the hashes).
- The weights are the original pinned checkpoint. An earlier local run on the ES-modified checkpoint
  (not stored here) gave the same class structure with different hashes.
