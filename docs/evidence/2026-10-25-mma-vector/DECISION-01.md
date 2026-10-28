# Decision: retain the selected projection source

Speed ratios new/old, B1 / B8 / B32. ABBA in one process, one live FP16 model, explicit separate compiled caches;
six timed observations per variant, synchronized host wall, fixed common 32-output-token benchmark.

|Model|5070 Ti|3060 WSL2|
|---|---|---|
| smol | 0.999 / 1.006 / 1.011 | 0.997 / 0.963 / 1.037 |
| tiny | 0.999 / 1.038 / 1.064 | 1.001 / 0.961 / 0.961 |
| qwen | 1.008 / 1.014 / 1.051 | 0.961 / 1.007 / 1.068 |

Aligned 64-bit MMA live-weight loads improve local B32 by 1.1–6.4%, but TinyLlama on 3060 regresses about 4%
at B8/B32; other 3060 cases are mixed. Do not select a uniform policy or add model-name-specific exceptions.
The candidate passes all 71 operator tests on each GPU, including existing unaligned/tail MMA oracles.

All parent tokens and final logit hashes match within each device and across both GPUs for all measured batches
and three models; consumed file manifests/prompts match and every compiled PTX/SASS audit passes.
See cross-gpu-comparison-01.json. This does not replace finite candidate/restore, native or managed qualification.
The selected numerical runtime remains 3fd704a5. Neither experiment is included in its published throughput.
Projection remains the primary bottleneck; these changes alone cannot close the 3.7–4.3x default-vLLM B32 gap.
