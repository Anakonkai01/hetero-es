# Final test runs of 09/10/2026 (commit `ade612e` plus documents)

Written by the AI. The full test suite with the real model (`HETEROES_QWEN_PINNED_PATH`, no end-to-end cases), on the code of the branch `feat/to-90-c1-profile` at `ade612e`:

| machine | result | log |
|---|---|---|
| 5070 Ti (`heteroes-match`) | **2087 passed, 4 skipped** in 118 s | `tests-5070ti.log` |
| 3060 (WSL2, with `LD_LIBRARY_PATH` for the Windows driver) | **2085 passed, 4 skipped, 2 failed** in 161 s | `tests-3060.log` |
| 1660S | **not run**: the machine went down three times in the last hours (see `../2026-10-09-three-machines/README.md`); its last full run is 2023 passed, 4 skipped at `555fb72`, before the later tests | - |

The two failures on the 3060 are `test_qwen_candidate_matches_all_the_recorded_evidence` and `test_base_model_reproduces_the_probe_outputs_text_for_text`: they compare the FP16 evaluation with the answers recorded on 2026-09-29 and one answer differs on that GPU (the known FP16 difference between GPUs; FP32 is the default and agrees on all three).
