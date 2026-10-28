# Decision: retain the selected projection source

Speed ratios new/old, B1 / B8 / B32. ABBA in one process, one live FP16 model, explicit separate compiled caches;
six timed observations per variant, synchronized host wall, fixed common 32-output-token benchmark.

|Model|5070 Ti|3060 WSL2|
|---|---|---|
| smol | 1.036 / 1.000 / 0.999 | 0.970 / 1.004 / 0.997 |
| tiny | 1.113 / 1.001 / 1.001 | 0.970 / 0.997 / 1.003 |
| qwen | 1.059 / 1.000 / 0.998 | 0.990 / 1.013 / 0.994 |

Four-product SIMT scheduling improves B1 on 5070 Ti by 3.6–11.3%, but regresses the three 3060 B1 cases by
1.0–3.0%. Other batch paths are unchanged; their small observed differences illustrate measurement variation.
Do not select a uniform policy or infer a generic speedup. Keep the variant for later architecture/resource study.
New aligned/offset/tail/all-split oracle coverage first passes the original source (24 tests), then the candidate
(71 tests locally; 24 targeted tests remotely). Three scratch fault mutants are killed after a passing control.

All parent tokens and final logit hashes match within each device and across both GPUs for all measured batches
and three models; consumed file manifests/prompts match and every compiled PTX/SASS audit passes.
See cross-gpu-comparison-01.json. This does not replace finite candidate/restore, native or managed qualification.
The selected numerical runtime remains 3fd704a5. Neither experiment is included in its published throughput.
Projection remains the primary bottleneck; these changes alone cannot close the 3.7–4.3x default-vLLM B32 gap.
